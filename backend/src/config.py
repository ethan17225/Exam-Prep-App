from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — the Docker WORKDIR. Every runtime path derives from this so that
# uploads and documents keep resolving to /app/uploads and /app/Docs, which is
# where the compose volumes are mounted. Deriving them from a domain module's
# __file__ instead would silently place them inside the image layer.
BASE_DIR = Path(__file__).resolve().parent.parent

SHOW_DOCS_IN = {"local", "staging"}


def settings_config(env_prefix: str = "") -> SettingsConfigDict:
    """Shared `model_config` for every settings class in the app."""
    return SettingsConfigDict(env_prefix=env_prefix, env_file=BASE_DIR / ".env", extra="ignore")


def load_settings[SettingsT: BaseSettings](cls: type[SettingsT], hint: str = "") -> SettingsT:
    """Instantiate a settings class, or exit with a readable message.

    Every config module goes through this: a missing or malformed value should
    print what is wrong and how to fix it, not a raw pydantic traceback buried in
    a container log.
    """
    try:
        return cls()
    except ValidationError as exc:
        message = f"Invalid settings for {cls.__name__}:\n{exc}"
        raise SystemExit(f"{message}\n\n{hint}" if hint else message) from exc


class Settings(BaseSettings):
    """App-wide settings.

    Deliberately has no env_prefix: DATABASE_URL and LOG_LEVEL are read by
    docker-compose, the entrypoint, Alembic and the tests. Per-domain prefixes
    (AUTH_, EXAMS_, DOCS_) apply to the domain configs, which are not shared.
    """

    model_config = settings_config()

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/mcq_app"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    log_level: str = "INFO"
    # Fails closed: an unset ENVIRONMENT must not publish the API schema.
    # docker-compose passes "production" explicitly; `local` is opt-in.
    environment: str = "production"


settings = load_settings(Settings)
