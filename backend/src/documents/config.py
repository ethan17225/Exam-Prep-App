from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config import BASE_DIR


class DocumentsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCS_", env_file=BASE_DIR / ".env", extra="ignore")

    # Must resolve to /app/Docs in Docker — that is where the `docs` volume is
    # mounted. Deriving it from this module's __file__ would put it inside the
    # image layer, and every course document would vanish on the next rebuild.
    root: Path = BASE_DIR / "Docs"


documents_settings = DocumentsConfig()
