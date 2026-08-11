from fastapi import APIRouter, Response, status

from src.auth import service
from src.auth.constants import AUTH_COOKIE
from src.auth.dependencies import CurrentUserDep
from src.auth.exceptions import BadCredentials, EmailTaken, InvalidInviteCode, RegistrationClosed
from src.auth.schemas import LoginIn, LogoutOut, RegisterIn, TokenOut, UserOut
from src.database import SessionDep

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
    return service.login_response(user)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Sign in",
    description="Exchanges email and password for a bearer token valid for 12 hours.",
    responses={status.HTTP_401_UNAUTHORIZED: {"description": BadCredentials.DETAIL}},
)
async def login(payload: LoginIn, db: SessionDep):
    user = await service.authenticate(payload, db)
    return service.login_response(user)


@router.post(
    "/logout",
    response_model=LogoutOut,
    summary="Sign out",
    description="Clears the auth cookie. The bearer token is discarded client-side.",
)
async def logout(response: Response) -> LogoutOut:
    response.delete_cookie(AUTH_COOKIE, path="/")
    return LogoutOut(ok=True)


@router.get(
    "/me",
    response_model=UserOut,
    summary="Current account",
    description="Returns the authenticated user's id, email and role.",
)
async def read_me(user: CurrentUserDep):
    return service.user_to_dict(user)
