from pathlib import Path

from pydantic_settings import BaseSettings

from src.config import BASE_DIR, load_settings, settings_config


class ExamsConfig(BaseSettings):
    model_config = settings_config("EXAMS_")

    # Must resolve to /app/uploads in Docker — that is where the `uploads` volume
    # is mounted. Deriving it from this module's __file__ would put it inside the
    # image layer, and every upload would vanish on the next rebuild.
    uploads_dir: Path = BASE_DIR / "uploads"
    max_image_bytes: int = 5 * 1024 * 1024


exams_settings = load_settings(ExamsConfig)
