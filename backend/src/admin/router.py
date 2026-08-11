from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from src.admin import service
from src.auth.dependencies import InstructorDep
from src.auth.exceptions import InstructorRequired
from src.database import SessionDep

router = APIRouter(prefix="/api/admin", tags=["admin"])


class DashboardItemOut(BaseModel):
    id: str
    exam_id: str
    exam_title: str
    student_email: str | None
    mode: str
    total_questions: int
    answered_count: int
    remaining_count: int
    correct_count: int
    wrong_count: int
    score_percent: float
    started_at: str | None
    saved_at: str
    seconds_since_last_answer: int
    seconds_since_start: int | None
    remaining_seconds: int


@router.get(
    "/dashboard",
    response_model=list[DashboardItemOut],
    summary="Live attempt dashboard",
    description=(
        "Every student's in-progress attempt with live grading. The only endpoint "
        "that returns other users' data, hence the instructor gate."
    ),
    responses={status.HTTP_403_FORBIDDEN: {"description": InstructorRequired.DETAIL}},
)
async def admin_dashboard(user: InstructorDep, db: SessionDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200):
    return await service.build_dashboard(limit, db)
