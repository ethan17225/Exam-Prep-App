from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.config import auth_settings
from src.auth.constants import AUTH_COOKIE, JWT_ALGORITHM, UserRole
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
