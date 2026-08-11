from pydantic import BaseModel

from src.schemas import ISODateTime


class DashboardItemOut(BaseModel):
    """One student's live attempt. Built by `service.build_dashboard` — the
    counts come from re-grading, so this is not a projection of a row."""

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
    started_at: ISODateTime | None
    saved_at: ISODateTime
    seconds_since_last_answer: int
    seconds_since_start: int | None
    remaining_seconds: int
