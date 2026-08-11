from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config import BASE_DIR


class ExamsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXAMS_", env_file=BASE_DIR / ".env", extra="ignore")

    # Must resolve to /app/uploads in Docker — that is where the `uploads` volume
    # is mounted. Deriving it from this module's __file__ would put it inside the
    # image layer, and every upload would vanish on the next rebuild.
    uploads_dir: Path = BASE_DIR / "uploads"
    max_image_bytes: int = 5 * 1024 * 1024


exams_settings = ExamsConfig()
