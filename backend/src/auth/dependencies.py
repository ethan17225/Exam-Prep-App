from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from src.auth import service
from src.auth.constants import UserRole
from src.auth.exceptions import InstructorRequired, InvalidToken, NotAuthenticated
from src.auth.models import User
from src.auth.utils import bearer_token
from src.database import SessionDep


async def get_current_user(request: Request, db: SessionDep) -> User:
    token = bearer_token(request)
    if not token:
        raise NotAuthenticated()
    user = await service.user_from_token(token, db)
    if not user:
        raise InvalidToken()
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_instructor(user: CurrentUserDep) -> User:
    # async despite doing no I/O: a sync dependency would be dispatched to the
    # threadpool on every instructor route for nothing.
    if user.role != UserRole.INSTRUCTOR:
        raise InstructorRequired()
    return user


InstructorDep = Annotated[User, Depends(require_instructor)]


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
            token = bearer_token(request)
            if not token:
                return JSONResponse({"detail": NotAuthenticated.DETAIL}, status_code=401)
            if not service.decode_token(token):
                return JSONResponse({"detail": InvalidToken.DETAIL}, status_code=401)
        # Only token decoding happens here — no I/O, so async is safe.
        return await call_next(request)

    return protect_static_mounts
