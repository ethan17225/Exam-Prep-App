from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.config import auth_settings
from src.auth.constants import AUTH_COOKIE, JWT_ALGORITHM, REGISTRABLE_ROLES, STAFF_ROLES, UserRole
from src.auth.exceptions import (
    AvatarTooLarge,
    BadCredentials,
    EmailTaken,
    InvalidInviteCode,
    RegistrationClosed,
    UnsupportedAvatarType,
)
from src.auth.models import User
from src.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from src.config import settings
from src.identifiers import new_id
from src.storage import (
    ALLOWED_IMAGE_EXTENSIONS,
    remove_upload_file,
    save_upload,
    storage_settings,
    upload_filename,
    upload_url,
    validated_extension,
)

TOKEN_TTL = timedelta(hours=auth_settings.token_ttl_hours)

# A real bcrypt hash of a value nobody can supply, verified against when the
# account does not exist so that login costs the same either way.
_DUMMY_HASH = bcrypt.hashpw(uuid4().hex.encode(), bcrypt.gensalt()).decode("utf-8")


def _hash_password_sync(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _verify_password_sync(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))


async def hash_password(password: str) -> str:
    # bcrypt is ~250ms of pure CPU at the default cost; running it inline would
    # stall the event loop for every other request on this worker.
    return await run_in_threadpool(_hash_password_sync, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await run_in_threadpool(_verify_password_sync, password, password_hash)


def create_token(user: User) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": user.id, "role": user.role, "ver": user.token_version, "iat": now, "exp": now + TOKEN_TTL},
        auth_settings.secret.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, auth_settings.secret.get_secret_value(), algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None


async def user_from_token(token: str, db: AsyncSession) -> User | None:
    payload = decode_token(token)
    if not payload:
        return None
    user = await get_by_id(payload.get("sub"), db)
    if not user:
        return None
    # A token minted before the last password change or sign-out-everywhere is
    # dead, even though its signature and expiry are still valid.
    if payload.get("ver") != user.token_version:
        return None
    return user


async def get_by_id(user_id: str | None, db: AsyncSession) -> User | None:
    if not user_id:
        return None
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def _instructor_by_invite_code(code: str, db: AsyncSession) -> User | None:
    if not code:
        return None
    stmt = select(User).where(User.invite_code == code, User.role == UserRole.INSTRUCTOR)
    return (await db.execute(stmt)).scalar_one_or_none()


async def register(payload: RegisterIn, db: AsyncSession) -> User:
    # Repeats RegisterIn's validator on purpose. The branch below stores whatever
    # role it is handed, so an admin reaching it would be a privilege escalation
    # rather than a validation slip — worth failing twice for.
    if payload.role not in REGISTRABLE_ROLES:
        raise RegistrationClosed()

    if payload.role is UserRole.INSTRUCTOR:
        # Instructors are gated by the deployment-wide code. Without it nobody can
        # self-promote, which is the whole point of keeping the two paths apart.
        if not auth_settings.instructor_invite_code:
            raise RegistrationClosed()
        if payload.invite_code != auth_settings.instructor_invite_code:
            raise InvalidInviteCode()
        instructor_id, own_code = None, new_id()
    else:
        # A student's invite code IS an instructor's personal code: it is both the
        # gate and the enrolment link, so a student can never exist without an
        # instructor, and the same wrong-code 403 covers both failures.
        instructor = await _instructor_by_invite_code(payload.invite_code, db)
        if not instructor:
            raise InvalidInviteCode()
        instructor_id, own_code = instructor.id, None

    email = payload.email.strip().lower()
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise EmailTaken()

    user = User(
        id=new_id(),
        email=email,
        password_hash=await hash_password(payload.password),
        role=payload.role,
        # Left unset on purpose: NULL is what sends the new account to onboarding.
        display_name=None,
        invite_code=own_code,
        instructor_id=instructor_id,
        created_at=datetime.now(),
    )
    db.add(user)
    await db.commit()
    return user


async def authenticate(payload: LoginIn, db: AsyncSession) -> User:
    email = payload.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    # Verify against a dummy hash when the account does not exist, so an unknown
    # address costs the same ~250ms as a known one. Short-circuiting here made
    # the two distinguishable in a single request.
    ok = await verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        raise BadCredentials()
    return user


async def change_password(user: User, new_password: str, db: AsyncSession) -> None:
    user.password_hash = await hash_password(new_password)
    # Every existing token for this account stops working.
    user.token_version += 1
    await db.commit()


async def revoke_tokens(user: User, db: AsyncSession) -> None:
    user.token_version += 1
    await db.commit()


# ── Profile ───────────────────────────────────────────────────────


async def build_me(user: User, db: AsyncSession) -> dict:
    """The one place MeOut's computed shape is assembled.

    `instructor_name` is the only non-column field, and resolving it costs a
    single keyed lookup — which is why login and register return the plain
    UserOut instead of paying for it on every sign-in.
    """
    instructor_name = None
    if user.instructor_id:
        instructor = await get_by_id(user.instructor_id, db)
        if instructor:
            instructor_name = instructor.display_name or instructor.email

    return {
        **UserOut.model_validate(user).model_dump(),
        "instructor_name": instructor_name,
    }


async def set_display_name(user: User, display_name: str, db: AsyncSession) -> User:
    user.display_name = display_name.strip()
    await db.commit()
    return user


async def replace_avatar(user: User, file: UploadFile, db: AsyncSession) -> User:
    ext = validated_extension(file.filename)
    if not ext:
        raise UnsupportedAvatarType(f"Unsupported image type. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}")

    filename = upload_filename(f"u{user.id}", ext)
    dest = storage_settings.dir / filename
    try:
        # One threadpool hop for the whole streamed write, not one per chunk.
        await run_in_threadpool(save_upload, file.file, dest, storage_settings.max_image_bytes)
    except ValueError as exc:
        raise AvatarTooLarge(f"Image exceeds the {storage_settings.max_image_bytes // (1024 * 1024)} MB limit") from exc

    previous = user.avatar
    user.avatar = upload_url(filename)
    await db.commit()
    # Only discard the old file once the new one is safely committed.
    await run_in_threadpool(remove_upload_file, previous)
    return user


async def clear_avatar(user: User, db: AsyncSession) -> User:
    previous = user.avatar
    user.avatar = None
    await db.commit()
    await run_in_threadpool(remove_upload_file, previous)
    return user


async def list_students(instructor_id: str, db: AsyncSession, limit: int = 500) -> list[User]:
    """The instructor's own students. Every analytics query is scoped by this same
    predicate, so a student never appears on another instructor's page."""
    stmt = (
        select(User)
        .where(User.instructor_id == instructor_id, User.role == UserRole.STUDENT)
        .order_by(User.created_at)
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


# ── Administration ────────────────────────────────────────────────
#
# Every function below crosses users, and each is reached only through the
# admin-gated platform router. They live here because `user` is this domain's
# table: `platform_admin.service` composes services and imports no models, the
# same way `admin.service` does. There is no per-caller predicate to apply —
# the route gate *is* the boundary for these, unlike the instructor analytics
# above, which carry their own `instructor_id` filter.


def _user_filters(query: str | None, role: UserRole | None) -> list:
    filters = []
    if role:
        filters.append(User.role == role)
    if query and (needle := query.strip().lower()):
        pattern = f"%{needle}%"
        # lower(NULL) LIKE ... is NULL, so an un-onboarded account simply fails
        # the name half of the OR rather than dropping out of the result set.
        filters.append(or_(func.lower(User.email).like(pattern), func.lower(User.display_name).like(pattern)))
    return filters


async def search_users(
    db: AsyncSession,
    query: str | None = None,
    role: UserRole | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[User]:
    stmt = select(User).where(*_user_filters(query, role)).order_by(User.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def count_users(db: AsyncSession, query: str | None = None, role: UserRole | None = None) -> int:
    return await db.scalar(select(func.count(User.id)).where(*_user_filters(query, role))) or 0


async def role_counts(db: AsyncSession) -> dict[str, int]:
    """Accounts per role. Column-tuple select, so no `.scalars()` here."""
    return dict((await db.execute(select(User.role, func.count(User.id)).group_by(User.role))).all())


async def count_pending_onboarding(db: AsyncSession) -> int:
    """Accounts that registered but never chose a preferred name, so every sign-in
    sends them back to onboarding. Worth a number on the admin dashboard: it is
    otherwise invisible and looks like people signing up and never returning."""
    return await db.scalar(select(func.count(User.id)).where(User.display_name.is_(None))) or 0


async def users_by_ids(user_ids, db: AsyncSession) -> dict[str, User]:
    """Keyed by id, for pages that list content and need its owner's name.

    One query for a whole page rather than one per row, and it lets the `exams`
    and `courses` services stay unaware of who owns what.
    """
    ids = list(user_ids)
    if not ids:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {user.id: user for user in rows}


async def list_staff(db: AsyncSession, limit: int = 500) -> list[User]:
    """Instructors, for the owner and reassignment pickers. Admins do not teach."""
    stmt = select(User).where(User.role.in_(STAFF_ROLES)).order_by(User.created_at).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def student_counts_by_instructor(db: AsyncSession) -> dict[str, int]:
    stmt = (
        select(User.instructor_id, func.count(User.id))
        .where(User.role == UserRole.STUDENT, User.instructor_id.is_not(None))
        .group_by(User.instructor_id)
    )
    return dict((await db.execute(stmt)).all())


async def create_account(
    email: str,
    password: str,
    role: UserRole,
    display_name: str | None,
    instructor_id: str | None,
    db: AsyncSession,
) -> User:
    """The admin-side account mint. Unlike `register` it takes no invite code —
    the admin gate replaces it — and it may create any role, including another
    admin. It also sets `display_name` directly, so an account created here can
    skip onboarding.

    An instructor still gets a personal enrolment code; a student still needs an
    instructor, and the caller validates that the id it passes is one.
    """
    normalized = email.strip().lower()
    if (await db.execute(select(User).where(User.email == normalized))).scalar_one_or_none():
        raise EmailTaken()

    user = User(
        id=new_id(),
        email=normalized,
        password_hash=await hash_password(password),
        role=role,
        display_name=(display_name.strip() or None) if display_name else None,
        # Only a student is enrolled with somebody; the column stays NULL for
        # instructors and admins. An admin is not a class and has no code.
        instructor_id=instructor_id if role is UserRole.STUDENT else None,
        invite_code=new_id() if role is UserRole.INSTRUCTOR else None,
        created_at=datetime.now(),
    )
    db.add(user)
    await db.commit()
    return user


async def set_role(user: User, role: UserRole, db: AsyncSession) -> User:
    """Change a role, and revoke every token the account holds.

    The JWT carries `role`, and the frontend renders its nav from the cached copy
    in the token's user payload. Authorization itself always reads the row, so a
    stale token cannot grant anything — but leaving one alive would show a
    demoted instructor an admin nav until it expired.
    """
    user.role = role
    if role is UserRole.INSTRUCTOR:
        # Without a code of their own an instructor cannot enrol anybody.
        if not user.invite_code:
            user.invite_code = new_id()
    else:
        # A student or admin holding an enrolment code could enrol other
        # students under themselves, which is what the code is the gate against.
        user.invite_code = None

    if role is not UserRole.STUDENT:
        user.instructor_id = None

    user.token_version += 1
    await db.commit()
    return user


async def set_instructor(user: User, instructor_id: str | None, db: AsyncSession) -> User:
    user.instructor_id = instructor_id
    await db.commit()
    return user


async def set_password(user: User, new_password: str, db: AsyncSession) -> User:
    """Admin reset. `change_password` is the self-service path and needs the
    current password; this one does not, so it is deliberately separate rather
    than a flag on that function."""
    user.password_hash = await hash_password(new_password)
    user.token_version += 1
    await db.commit()
    return user


async def rotate_invite_code(user: User, db: AsyncSession) -> User:
    """Mint a fresh enrolment code. Already-enrolled students keep their link —
    `instructor_id` is what that link is, not the code."""
    user.invite_code = new_id()
    await db.commit()
    return user


async def reassign_students(from_instructor_id: str, to_instructor_id: str, db: AsyncSession) -> int:
    """Move a whole roster, returning how many students moved.

    A bulk UPDATE rather than a loop: the alternative loads a class into memory to
    write one column on each row.
    """
    result = await db.execute(
        update(User)
        .where(User.instructor_id == from_instructor_id, User.role == UserRole.STUDENT)
        .values(instructor_id=to_instructor_id)
    )
    await db.commit()
    return result.rowcount or 0


async def delete_account(user: User, db: AsyncSession) -> None:
    """Remove an account and everything cascading from it.

    The FKs do the work: courses, exams (and their questions), history and open
    attempts are ON DELETE CASCADE, while other users' `instructor_id` and the
    audit log's `actor_id` are ON DELETE SET NULL — a deleted instructor must not
    take their students' accounts with them, and a deleted admin must not erase
    the record of what they did.
    """
    avatar = user.avatar
    await db.delete(user)
    await db.commit()
    # Only after the row is certainly gone, like every other unlink in the app.
    await run_in_threadpool(remove_upload_file, avatar)


def login_response(user: User) -> JSONResponse:
    token = create_token(user)
    # mode="json" so the role StrEnum and any future non-primitive renders the
    # same way it would through a response_model.
    body = TokenOut(token=token, user=UserOut.model_validate(user)).model_dump(mode="json")
    response = JSONResponse(body)
    # This cookie exists only so <img src> and <a href> can authenticate against
    # the two StaticFiles mounts; it cannot drive an /api/* route. Secure is off
    # only for local HTTP development — any other environment must be HTTPS.
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=int(TOKEN_TTL.total_seconds()),
        httponly=True,
        secure=settings.environment != "local",
        samesite="lax",
        path="/",
    )
    return response
