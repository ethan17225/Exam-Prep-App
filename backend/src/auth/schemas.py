from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.auth.constants import UserRole
from src.auth.models import DISPLAY_NAME_MAX


class RegisterIn(BaseModel):
    email: EmailStr
    # bcrypt hard-limits input at 72 bytes; anything longer is silently ignored,
    # so reject it rather than accept a password that is not fully checked.
    password: str = Field(min_length=8, max_length=72)
    # For a student this is their instructor's personal code, which links the two;
    # for an instructor it is AUTH_INSTRUCTOR_INVITE_CODE.
    invite_code: str = Field(max_length=200)
    role: UserRole = UserRole.STUDENT


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class PasswordChangeIn(BaseModel):
    # The current password is required so a borrowed session cannot lock the real
    # owner out by changing it.
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class ProfileUpdate(BaseModel):
    # min_length=1 after the service strips: onboarding requires a real name, and
    # a whitespace-only one would leave the account looking un-onboarded forever.
    display_name: str = Field(min_length=1, max_length=DISPLAY_NAME_MAX)


class UserOut(BaseModel):
    """Plain columns only, so login and register can return it without a second
    query. `avatar` and `invite_code` are read-only outputs — see the model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    role: UserRole
    # None until onboarding sets it; the frontend guard reads exactly that.
    display_name: str | None
    avatar: str | None
    # An instructor's own enrolment code. Always None for a student — the column
    # is only ever populated for instructors.
    invite_code: str | None


class MeOut(UserOut):
    """Adds the one field that is not a column. Assembled by
    `service.build_me`, which is the only place this shape is built."""

    instructor_name: str | None


class TokenOut(BaseModel):
    token: str
    user: UserOut


class AvatarOut(BaseModel):
    avatar: str | None


class LogoutOut(BaseModel):
    ok: bool
