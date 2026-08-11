from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.admin import service
from src.admin.schemas import DashboardItemOut
from src.attempts import service as attempts_service
from src.attempts.exceptions import RecordNotFound
from src.auth.dependencies import require_instructor
from src.auth.exceptions import InstructorRequired
from src.database import SessionDep
from src.schemas import DeletedOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get(
    "/dashboard",
    response_model=list[DashboardItemOut],
    summary="Live attempt dashboard",
    description=(
        "Every student's in-progress attempt with live grading. The only endpoint "
        "that returns other users' data, hence the instructor gate."
    ),
    # The gate is the whole point here, but the identity is never read — so it is
    # a route dependency rather than an unused parameter.
    dependencies=[Depends(require_instructor)],
    responses={status.HTTP_403_FORBIDDEN: {"description": InstructorRequired.DETAIL}},
)
async def admin_dashboard(db: SessionDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200):
    return await service.build_dashboard(limit, db)


@router.delete(
    "/in-progress/{record_id}",
    response_model=DeletedOut,
    summary="Reset a student's attempt",
    description=(
        "Clears any student's in-progress attempt. The companion to students not "
        "being able to discard a graded attempt themselves — without this, an "
        "abandoned attempt would lock a student out of that exam permanently."
    ),
    dependencies=[Depends(require_instructor)],
    responses={
        status.HTTP_403_FORBIDDEN: {"description": InstructorRequired.DETAIL},
        status.HTTP_404_NOT_FOUND: {"description": RecordNotFound.DETAIL},
    },
)
async def reset_attempt(record_id: str, db: SessionDep):
    await attempts_service.reset_attempt_unscoped(record_id, db)
    return {"deleted": True}
