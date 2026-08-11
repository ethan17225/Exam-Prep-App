from pydantic import BaseModel, EmailStr, Field

from src.auth.constants import UserRole


class RegisterIn(BaseModel):
    email: EmailStr
    # bcrypt hard-limits input at 72 bytes; anything longer is silently ignored,
    # so reject it rather than accept a password that is not fully checked.
    password: str = Field(min_length=8, max_length=72)
    invite_code: str = Field(max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: UserRole


class TokenOut(BaseModel):
    token: str
    user: UserOut


class LogoutOut(BaseModel):
    ok: bool
