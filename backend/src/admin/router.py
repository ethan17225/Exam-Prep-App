from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.admin import service
from src.admin.exceptions import StudentNotFound
from src.admin.schemas import (
    DashboardItemOut,
    InstructorOverviewOut,
    StudentDetailOut,
    StudentItemOut,
)
from src.attempts import service as attempts_service
from src.attempts.exceptions import RecordNotFound
from src.auth.dependencies import InstructorDep, require_instructor
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


@router.get(
    "/overview",
    response_model=InstructorOverviewOut,
    summary="Instructor overview",
    description=(
        "Class-wide aggregates for the caller's own students: headline counts, "
        "14 days of activity, the score distribution, per-exam rollups and the "
        "weakest topics. Every figure is scoped to students enrolled with the "
        "caller's invite code."
    ),
    responses={status.HTTP_403_FORBIDDEN: {"description": InstructorRequired.DETAIL}},
)
async def instructor_overview(user: InstructorDep, db: SessionDep):
    return await service.build_instructor_overview(user, db)


@router.get(
    "/students",
    response_model=list[StudentItemOut],
    summary="List your students",
    description=(
        "The caller's students with their aggregates. Students who have not sat "
        "anything yet are included with zeroed counts."
    ),
    responses={status.HTTP_403_FORBIDDEN: {"description": InstructorRequired.DETAIL}},
)
async def list_students(user: InstructorDep, db: SessionDep):
    return await service.build_students(user, db)


@router.get(
    "/students/{student_id}",
    response_model=StudentDetailOut,
    summary="One student's detail",
    description=(
        "Recent attempts and per-topic performance for one of the caller's own "
        "students. A student enrolled with another instructor is a 404."
    ),
    responses={
        status.HTTP_403_FORBIDDEN: {"description": InstructorRequired.DETAIL},
        status.HTTP_404_NOT_FOUND: {"description": StudentNotFound.DETAIL},
    },
)
async def student_detail(student_id: str, user: InstructorDep, db: SessionDep):
    return await service.build_student_detail(user, student_id, db)


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
