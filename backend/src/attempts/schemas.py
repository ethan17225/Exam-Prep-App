from typing import Annotated, Any

from pydantic import BaseModel, Field

from src.constants import MAX_INT, MAX_QUESTIONS_PER_EXAM


class AnswerSubmission(BaseModel):
    question_number: int = Field(ge=0, le=MAX_INT)
    answer: Any = None
    fib_correct: bool | None = None


class ExamSubmission(BaseModel):
    exam_id: str = Field(max_length=8)
    answers: list[AnswerSubmission] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    time_spent_seconds: int = Field(ge=0, le=MAX_INT)
    mode: str = Field(default="exam", max_length=10)
    question_numbers: list[int] | None = Field(default=None, max_length=MAX_QUESTIONS_PER_EXAM)


class SaveProgressPayload(BaseModel):
    exam_id: str = Field(max_length=8)
    mode: str = Field(default="exam", max_length=10)
    # Keys are question numbers. Constraining them here stops a non-numeric key
    # from wedging the admin dashboard's int() conversion for every instructor.
    answers: dict[Annotated[int, Field(ge=0, le=MAX_INT)], Any]
    flagged: list[int] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    question_order: list[int] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    remaining_seconds: int = Field(ge=0, le=MAX_INT)
    current_page: int = Field(default=0, ge=0, le=MAX_INT)


class InProgressOut(BaseModel):
    id: str
    exam_id: str
    exam_title: str
    mode: str
    answers: Any
    flagged: Any
    question_order: Any
    remaining_seconds: int
    current_page: int
    total_questions: int
    answered_count: int
    started_at: str | None
    saved_at: str


class HistorySummaryOut(BaseModel):
    id: str
    exam_id: str
    exam_title: str
    score: float
    correct: int
    total: int
    passed: bool
    time_spent_seconds: int
    mode: str
    taken_at: str


class HistoryOut(HistorySummaryOut):
    """Full record, including the per-question results blob. Returned only for a
    single record — the list endpoint would be a 100 MB response."""

    results: Any


class TopicStatOut(BaseModel):
    topic: str
    total: int
    correct: int
    score: int


class DeletedOut(BaseModel):
    deleted: bool
