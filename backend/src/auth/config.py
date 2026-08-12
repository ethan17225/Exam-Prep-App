from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

from src.config import load_settings, settings_config


class AuthConfig(BaseSettings):
    model_config = settings_config("AUTH_")

    # AUTH_SECRET. 32 chars is the HMAC-SHA256 key length; PyJWT warns below it.
    # SecretStr so a rejected value is never echoed into a crash log — pydantic
    # includes input_value in its error text, and the container crash-loops.
    secret: SecretStr = Field(min_length=32)

    # AUTH_INSTRUCTOR_INVITE_CODE. Gates instructor sign-ups only. Students
    # register with their instructor's personal code instead, which is both the
    # gate and the enrolment link — so there is no shared student code any more,
    # and no way to create a student who belongs to nobody.
    #
    # Empty closes instructor registration. It does NOT close student
    # registration: an instructor's code is minted at their sign-up and revoking
    # enrolment is done by rotating that, not by blanking this.
    instructor_invite_code: str = ""

    # Long-lived on purpose: exams run 90-180 minutes and there is no refresh
    # token, so a token expiring mid-exam is the one failure that costs a student
    # their answers.
    token_ttl_hours: int = 12


auth_settings = load_settings(
    AuthConfig,
    'Generate a secret with: python -c "import secrets; print(secrets.token_urlsafe(48))"',
)
