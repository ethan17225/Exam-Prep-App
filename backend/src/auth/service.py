from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.config import auth_settings
from src.auth.constants import AUTH_COOKIE, JWT_ALGORITHM, UserRole
from src.auth.exceptions import BadCredentials, EmailTaken, InvalidInviteCode, RegistrationClosed
from src.auth.models import User
from src.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from src.config import settings
from src.identifiers import new_id

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


async def register(payload: RegisterIn, db: AsyncSession) -> User:
    if not auth_settings.invite_code:
        raise RegistrationClosed()
    if payload.invite_code != auth_settings.invite_code:
        raise InvalidInviteCode()

    email = payload.email.strip().lower()
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise EmailTaken()

    user = User(
        id=new_id(),
        email=email,
        password_hash=await hash_password(payload.password),
        role=UserRole.STUDENT,
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
