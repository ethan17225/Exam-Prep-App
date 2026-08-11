import logging

from fastapi import APIRouter, Response, status

from src.auth import service
from src.auth.constants import AUTH_COOKIE
from src.auth.dependencies import CurrentUserDep
from src.auth.exceptions import BadCredentials, EmailTaken, InvalidInviteCode, RegistrationClosed
from src.auth.schemas import LoginIn, LogoutOut, PasswordChangeIn, RegisterIn, TokenOut, UserOut
from src.config import settings
from src.database import SessionDep

# Auth outcomes are the only forensic record this app keeps. Without them a
# password-spray run or an account takeover leaves nothing behind.
logger = logging.getLogger("mcq.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenOut,
    summary="Register an account",
    description=(
        "Creates a student account. Requires the shared invite code. Returns the "
        "same token payload as login, and sets the auth cookie used by static files."
    ),
    responses={
        status.HTTP_403_FORBIDDEN: {"description": f"{RegistrationClosed.DETAIL} / {InvalidInviteCode.DETAIL}"},
        status.HTTP_409_CONFLICT: {"description": EmailTaken.DETAIL},
    },
)
async def register(payload: RegisterIn, db: SessionDep):
    # Returns a JSONResponse directly so the auth cookie can be set, which means
    # FastAPI passes it through untouched — including its 200 status. Declaring
    # status_code=201 here would be a lie, as it was before this refactor.
    user = await service.register(payload, db)
    logger.info("register ok user=%s", user.id)
    return service.login_response(user)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Sign in",
    description="Exchanges email and password for a bearer token valid for 12 hours.",
    responses={status.HTTP_401_UNAUTHORIZED: {"description": BadCredentials.DETAIL}},
)
async def login(payload: LoginIn, db: SessionDep):
    try:
        user = await service.authenticate(payload, db)
    except BadCredentials:
        # Deliberately logs the attempted address, not the password.
        logger.warning("login failed email=%s", payload.email)
        raise
    logger.info("login ok user=%s", user.id)
    return service.login_response(user)


@router.post(
    "/logout",
    response_model=LogoutOut,
    summary="Sign out",
    description="Clears the auth cookie. The bearer token is discarded client-side.",
)
async def logout(response: Response) -> LogoutOut:
    # Attributes must match the ones used at set time or some browsers keep the
    # cookie. The bearer token is discarded client-side.
    response.delete_cookie(
        AUTH_COOKIE,
        path="/",
        httponly=True,
        secure=settings.environment != "local",
        samesite="lax",
    )
    return LogoutOut(ok=True)


@router.post(
    "/password",
    response_model=TokenOut,
    summary="Change your password",
    description=(
        "Requires the current password. Every existing token for the account is "
        "revoked, including the caller's — the response carries a fresh one."
    ),
    responses={status.HTTP_401_UNAUTHORIZED: {"description": BadCredentials.DETAIL}},
)
async def change_password(payload: PasswordChangeIn, user: CurrentUserDep, db: SessionDep):
    if not await service.verify_password(payload.current_password, user.password_hash):
        raise BadCredentials()
    await service.change_password(user, payload.new_password, db)
    logger.info("password changed user=%s (all tokens revoked)", user.id)
    return service.login_response(user)


@router.get(
    "/me",
    response_model=UserOut,
    summary="Current account",
    description="Returns the authenticated user's id, email and role.",
)
async def read_me(user: CurrentUserDep):
    return user
