from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.auth.dependencies import CurrentUserDep, get_current_user
from src.database import SessionDep
from src.documents import service
from src.documents.exceptions import DocumentNotFound
from src.documents.schemas import DocumentContentOut, DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get(
    "",
    response_model=list[DocumentOut],
    summary="List course documents",
    description=(
        "Scans the documents directory and pairs each PDF with its HTML "
        "rendering. Shared reading material: every signed-in user sees the same "
        "files, but the course each is attributed to respects visibility."
    ),
)
async def list_documents(user: CurrentUserDep, db: SessionDep, course_id: Annotated[str | None, Query()] = None):
    return await service.list_documents(user, course_id, db)


@router.get(
    "/html",
    response_model=DocumentContentOut,
    summary="Read a document's HTML",
    description="Returns the <body> of a rendered document. Paths are confined to the documents directory.",
    # Authentication only — this route needs no identity and touches no session,
    # so the gate is a route dependency rather than an unused parameter.
    dependencies=[Depends(get_current_user)],
    responses={status.HTTP_404_NOT_FOUND: {"description": DocumentNotFound.DETAIL}},
)
async def get_document_html(path: Annotated[str, Query()]):
    return await service.document_html(path)
