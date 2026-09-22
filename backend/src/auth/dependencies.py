from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from src.auth import service
from src.auth.constants import UserRole
from src.auth.exceptions import AdminRequired, InstructorRequired, InvalidToken, NotAuthenticated
from src.auth.models import User
from src.auth.utils import bearer_token, static_mount_token
from src.database import SessionDep


async def get_current_user(request: Request, db: SessionDep) -> User:
    token = bearer_token(request)
    if not token:
        raise NotAuthenticated()
    identities = await service.identities_from_token(token, db)
    if not identities:
        raise InvalidToken()
    user, actor = identities
    # Stash for AdminDep / ImpersonationActorDep so they need no second session
    # — and so dependency_overrides of get_current_user still leave those
    # gates DB-free in the no-Postgres unit tests.
    request.state.impersonation_actor = actor
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_impersonation_actor(request: Request) -> User | None:
    """The real admin behind an impersonation JWT, or None for a normal session.

    Reads the value `get_current_user` stashed on the request. Absent when that
    dependency was overridden (unit tests) or has not run yet.
    """
    return getattr(request.state, "impersonation_actor", None)


ImpersonationActorDep = Annotated[User | None, Depends(get_impersonation_actor)]


async def require_instructor(user: CurrentUserDep) -> User:
    # async despite doing no I/O: a sync dependency would be dispatched to the
    # threadpool on every instructor route for nothing.
    #
    # Exact role: an admin is not an instructor. Teaching routes are a class
    # view; the platform console is the admin's equivalent, behind AdminDep.
    # Equality, not identity: `user.role` is a String(10) column, so after a
    # round-trip through Postgres it is the str "instructor", not the enum
    # member. `is not UserRole.INSTRUCTOR` 403s every real instructor.
    if user.role != UserRole.INSTRUCTOR:
        raise InstructorRequired()
    return user


InstructorDep = Annotated[User, Depends(require_instructor)]


async def require_admin(request: Request, user: CurrentUserDep) -> User:
    """Gate for `/api/platform/*` — the only surface that can mutate another
    user's account, role or content.

    When the bearer is an impersonation token (`act` claim), the *actor* admin
    stashed by `get_current_user` is returned so platform routes stay usable
    without ending the session. Otherwise exact equality on the effective user:
    an instructor must not reach it.
    """
    actor = getattr(request.state, "impersonation_actor", None)
    if actor is not None:
        return actor
    if user.role != UserRole.ADMIN:
        raise AdminRequired()
    return user


AdminDep = Annotated[User, Depends(require_admin)]


def make_static_mount_guard(prefixes: Iterable[str]):
    """Build the middleware that authenticates the StaticFiles mounts.

    FastAPI dependencies do not apply to mounts, but middleware runs before
    routing, so it does. These URLs are loaded by <img src> and <a href>, which
    cannot carry an Authorization header — hence the cookie set at login.

    Takes the prefixes as an argument so `auth` need not import `exams` or
    `documents` for two string literals; `main` supplies them.

    ponytail: authentication only, not per-file authorization. A logged-in user
    could fetch another's question image by guessing the 10-hex-char filename.
    Upgrade path is FileResponse routes with an owner lookup per file.
    """
    guarded = tuple(prefixes)

    async def protect_static_mounts(request: Request, call_next):
        if request.url.path.startswith(guarded):
            token = static_mount_token(request)
            if not token:
                return JSONResponse({"detail": NotAuthenticated.DETAIL}, status_code=401)
            if not service.decode_token(token):
                return JSONResponse({"detail": InvalidToken.DETAIL}, status_code=401)
        # Only token decoding happens here — no I/O, so async is safe.
        return await call_next(request)

    return protect_static_mounts
