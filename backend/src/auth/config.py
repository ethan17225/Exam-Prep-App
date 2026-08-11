from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config import BASE_DIR


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=BASE_DIR / ".env", extra="ignore")

    # AUTH_SECRET. 32 chars is the HMAC-SHA256 key length; PyJWT warns below it.
    secret: str = Field(min_length=32)

    # AUTH_INVITE_CODE. Registration is gated by a shared code: it keeps the open
    # internet out without building email verification. Empty closes registration.
    invite_code: str = ""

    # Long-lived on purpose: exams run 90-180 minutes and there is no refresh
    # token, so a token expiring mid-exam is the one failure that costs a student
    # their answers.
    token_ttl_hours: int = 12


def _load() -> AuthConfig:
    try:
        return AuthConfig()
    except ValidationError as exc:
        raise SystemExit(
            f"Invalid auth settings:\n{exc}\n\n"
            'Generate a secret with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        ) from exc


auth_settings = _load()
