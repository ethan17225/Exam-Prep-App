from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

from src.config import load_settings, settings_config


class AuthConfig(BaseSettings):
    model_config = settings_config("AUTH_")

    # AUTH_SECRET. 32 chars is the HMAC-SHA256 key length; PyJWT warns below it.
    # SecretStr so a rejected value is never echoed into a crash log — pydantic
    # includes input_value in its error text, and the container crash-loops.
    secret: SecretStr = Field(min_length=32)

    # AUTH_INVITE_CODE. Registration is gated by a shared code: it keeps the open
    # internet out without building email verification. Empty closes registration.
    invite_code: str = ""

    # Long-lived on purpose: exams run 90-180 minutes and there is no refresh
    # token, so a token expiring mid-exam is the one failure that costs a student
    # their answers.
    token_ttl_hours: int = 12


auth_settings = load_settings(
    AuthConfig,
    'Generate a secret with: python -c "import secrets; print(secrets.token_urlsafe(48))"',
)
