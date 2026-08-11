import contextlib
import pathlib
from uuid import uuid4

from src.exams.config import exams_settings
from src.exams.constants import UPLOADS_URL_PREFIX


def image_filename(question_id: int, ext: str) -> str:
    return f"q{question_id}_{uuid4().hex[:10]}{ext}"


def image_url(filename: str) -> str:
    return f"{UPLOADS_URL_PREFIX}/{filename}"


def remove_image_file(image_url_value: str | None) -> None:
    if not image_url_value:
        return
    filename = image_url_value.rsplit("/", 1)[-1]
    path = exams_settings.uploads_dir / filename
    if path.is_file():
        # A file we cannot remove is not worth failing a request over.
        with contextlib.suppress(OSError):
            path.unlink()


def remove_image_files(image_urls) -> None:
    """Batch form, so deleting an exam costs one threadpool hop rather than N."""
    for value in image_urls:
        remove_image_file(value)


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
