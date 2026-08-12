"""Image uploads: where they live, what is allowed, and how bytes reach disk.

A pure leaf, like `grading/` — it imports nothing but `src.config`, which is what
lets both `auth` (avatars) and `exams` (question images) depend on it without an
import cycle. Anything question-specific stays in `exams/utils.py`.
"""

import contextlib
import pathlib
from uuid import uuid4

from pydantic_settings import BaseSettings

from src.config import BASE_DIR, load_settings, settings_config

# .svg is deliberately absent: SVGs are served from the same origin as the app,
# so a script inside one is stored XSS. This is a security decision, which is why
# it lives here and not in a settings class where an env var could widen it.
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Uploads are served under /api/... so the dev proxy and nginx forward them
# without extra rules.
UPLOADS_URL_PREFIX = "/api/uploads"


class StorageConfig(BaseSettings):
    model_config = settings_config("UPLOADS_")

    # Must resolve to /app/uploads in Docker — that is where the `uploads` volume
    # is mounted. Deriving it from this module's __file__ would put it inside the
    # image layer, and every upload would vanish on the next rebuild.
    dir: pathlib.Path = BASE_DIR / "uploads"
    max_image_bytes: int = 5 * 1024 * 1024


storage_settings = load_settings(StorageConfig)


def upload_filename(prefix: str, ext: str) -> str:
    """A name no caller can predict, so one user cannot address another's file."""
    return f"{prefix}_{uuid4().hex[:10]}{ext}"


def upload_url(filename: str) -> str:
    return f"{UPLOADS_URL_PREFIX}/{filename}"


def remove_upload_file(url_value: str | None) -> None:
    if not url_value:
        return
    filename = url_value.rsplit("/", 1)[-1]
    path = storage_settings.dir / filename
    if path.is_file():
        # A file we cannot remove is not worth failing a request over.
        with contextlib.suppress(OSError):
            path.unlink()


def remove_upload_files(url_values) -> None:
    """Batch form, so deleting an exam costs one threadpool hop rather than N."""
    for value in url_values:
        remove_upload_file(value)


def save_upload(src, dest: pathlib.Path, max_bytes: int) -> int:
    """Stream an upload to disk under a size cap.

    Fully synchronous and self-contained so the caller can hand the whole
    operation to one `run_in_threadpool` call rather than one hop per chunk.
    Raises on overflow; the partial file is removed here so no caller has to.
    """
    written = 0
    try:
        with dest.open("wb") as out:
            while chunk := src.read(64 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError("too large")
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return written


def validated_extension(filename: str | None) -> str:
    """The lowercased suffix, or "" when it is not an allowed image type.

    Callers raise their own domain exception — `auth` and `exams` report an
    unsupported upload with different error classes.
    """
    ext = pathlib.Path(filename or "").suffix.lower()
    return ext if ext in ALLOWED_IMAGE_EXTENSIONS else ""
