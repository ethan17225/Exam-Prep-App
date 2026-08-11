from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — the Docker WORKDIR. Every runtime path derives from this so that
# uploads and documents keep resolving to /app/uploads and /app/Docs, which is
# where the compose volumes are mounted. Deriving them from a domain module's
# __file__ instead would silently place them inside the image layer.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """App-wide settings.

    Deliberately has no env_prefix: DATABASE_URL and LOG_LEVEL are read by
    docker-compose, the entrypoint, Alembic and the tests. Per-domain prefixes
    (AUTH_, EXAMS_, DOCS_) apply to the domain configs, which are not shared.
    """

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/mcq_app"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    log_level: str = "INFO"
    # Anything outside this set serves no /docs, /redoc or /openapi.json.
    environment: str = "local"


def _load() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise SystemExit(f"Invalid application settings:\n{exc}") from exc


settings = _load()

SHOW_DOCS_IN = {"local", "staging"}
