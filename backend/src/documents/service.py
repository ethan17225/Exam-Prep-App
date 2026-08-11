from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.courses import service as courses_service
from src.documents.config import documents_settings
from src.documents.constants import DOCS_URL_PREFIX
from src.documents.exceptions import DocumentNotFound
from src.documents.utils import read_body_html, safe_resolve


def _scan(course_map: dict[str, dict]) -> list[dict]:
    """Walk Docs/<course>/pdf and pair each PDF with its HTML sibling.

    Entirely synchronous filesystem work — one threadpool hop for the whole walk
    rather than one per syscall.
    """
    root = documents_settings.root
    docs: list[dict] = []
    if not root.is_dir():
        return docs

    for course_dir in sorted(root.iterdir()):
        if not course_dir.is_dir():
            continue

        pdf_dir = course_dir / "pdf"
        html_dir = course_dir / "html"
        if not pdf_dir.is_dir():
            continue

        matched_course = course_map.get(course_dir.name)

        for pdf in sorted(pdf_dir.glob("*.pdf")):
            html_file = html_dir / (pdf.stem + ".html") if html_dir.is_dir() else None
            has_html = html_file is not None and html_file.is_file()
            docs.append(
                {
                    "filename": pdf.name,
                    "title": pdf.stem,
                    "pdf_url": f"{DOCS_URL_PREFIX}/{course_dir.name}/pdf/{pdf.name}",
                    "html_url": (f"{DOCS_URL_PREFIX}/{course_dir.name}/html/{pdf.stem}.html" if has_html else None),
                    "size_bytes": pdf.stat().st_size,
                    "course_id": matched_course["id"] if matched_course else None,
                    "course_name": matched_course["name"] if matched_course else course_dir.name,
                }
            )
    return docs


async def list_documents(user: User, course_id: str | None, db: AsyncSession) -> list[dict]:
    """Documents are keyed to courses by matching the folder name to a course
    name, so only the course association is filtered by visibility."""
    courses = await courses_service.list_visible(user, db)
    course_map = {c.name: {"id": c.id, "name": c.name} for c in courses}

    docs = await run_in_threadpool(_scan, course_map)
    if course_id:
        docs = [d for d in docs if d["course_id"] == course_id]
    return docs


async def document_html(path_param: str) -> dict:
    resolved = safe_resolve(documents_settings.root, path_param)
    if resolved is None:
        raise DocumentNotFound()
    if not resolved.is_file() or resolved.suffix.lower() != ".html":
        raise DocumentNotFound()

    body_html = await run_in_threadpool(read_body_html, resolved)
    return {"title": resolved.stem, "html": body_html}
