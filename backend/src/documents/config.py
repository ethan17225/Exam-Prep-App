from pathlib import Path

from pydantic_settings import BaseSettings

from src.config import BASE_DIR, load_settings, settings_config


class DocumentsConfig(BaseSettings):
    model_config = settings_config("DOCS_")

    # Must resolve to /app/Docs in Docker — that is where the `docs` volume is
    # mounted. Deriving it from this module's __file__ would put it inside the
    # image layer, and every course document would vanish on the next rebuild.
    root: Path = BASE_DIR / "Docs"


documents_settings = load_settings(DocumentsConfig)
