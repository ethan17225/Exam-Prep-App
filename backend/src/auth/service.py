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
from src.auth.schemas import LoginIn, RegisterIn

TOKEN_TTL = timedelta(hours=auth_settings.token_ttl_hours)


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
        {"sub": user.id, "role": user.role, "iat": now, "exp": now + TOKEN_TTL},
        auth_settings.secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, auth_settings.secret, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None


async def user_from_token(token: str, db: AsyncSession) -> User | None:
    payload = decode_token(token)
    if not payload:
        return None
    return await get_by_id(payload.get("sub"), db)


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
        id=str(uuid4())[:8],
        email=email,
        password_hash=await hash_password(payload.password),
        role=UserRole.STUDENT,
        created_at=datetime.now(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(payload: LoginIn, db: AsyncSession) -> User:
    email = payload.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or not await verify_password(payload.password, user.password_hash):
        raise BadCredentials()
    return user


def user_to_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role}


def login_response(user: User) -> JSONResponse:
    token = create_token(user)
    response = JSONResponse({"token": token, "user": user_to_dict(user)})
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=int(TOKEN_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response
