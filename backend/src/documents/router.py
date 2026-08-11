from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from src.auth.dependencies import CurrentUserDep
from src.database import SessionDep
from src.documents import service
from src.documents.exceptions import DocumentNotFound

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentOut(BaseModel):
    filename: str
    title: str
    pdf_url: str
    html_url: str | None
    size_bytes: int
    course_id: str | None
    course_name: str


class DocumentContentOut(BaseModel):
    title: str
    html: str


@router.get(
    "",
    response_model=list[DocumentOut],
    summary="List course documents",
    description=(
        "Scans the documents directory and pairs each PDF with its HTML "
        "rendering. Shared reading material: every signed-in user sees the same list."
    ),
)
async def list_documents(user: CurrentUserDep, db: SessionDep, course_id: Annotated[str | None, Query()] = None):
    return await service.list_documents(user, course_id, db)


@router.get(
    "/html",
    response_model=DocumentContentOut,
    summary="Read a document's HTML",
    description="Returns the <body> of a rendered document. Paths are confined to the documents directory.",
    responses={status.HTTP_404_NOT_FOUND: {"description": DocumentNotFound.DETAIL}},
)
async def get_document_html(user: CurrentUserDep, path: Annotated[str, Query()]):
    return await service.document_html(path)
