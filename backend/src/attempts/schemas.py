from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from src.attempts.constants import AttemptMode
from src.constants import MAX_INT, MAX_QUESTIONS_PER_EXAM
from src.identifiers import ID_LENGTH
from src.schemas import ISODateTime


class AnswerSubmission(BaseModel):
    question_number: int = Field(ge=0, le=MAX_INT)
    answer: Any = None
    # Honoured only in practice mode — a graded run cannot self-mark.
    fib_correct: bool | None = None


class ExamSubmission(BaseModel):
    exam_id: str = Field(max_length=ID_LENGTH)
    answers: list[AnswerSubmission] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    # Ignored for graded attempts: the server computes elapsed time from the
    # attempt's started_at, which the client cannot influence.
    time_spent_seconds: int = Field(ge=0, le=MAX_INT)
    mode: AttemptMode = AttemptMode.EXAM
    # Ignored for graded attempts: it let a student grade only the questions they
    # answered correctly, since `total` was the size of the chosen subset.
    question_numbers: list[int] | None = Field(default=None, max_length=MAX_QUESTIONS_PER_EXAM)


class SaveProgressPayload(BaseModel):
    exam_id: str = Field(max_length=ID_LENGTH)
    mode: AttemptMode = AttemptMode.EXAM
    # Keys are question numbers. Constraining them here stops a non-numeric key
    # from wedging the admin dashboard's int() conversion for every instructor.
    answers: dict[Annotated[int, Field(ge=0, le=MAX_INT)], Any]
    flagged: list[int] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    question_order: list[int] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    remaining_seconds: int = Field(ge=0, le=MAX_INT)
    current_page: int = Field(default=0, ge=0, le=MAX_INT)


class InProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    started_at: ISODateTime | None
    saved_at: ISODateTime


class HistorySummaryOut(BaseModel):
    """Everything the history list renders, minus the heavy `results` blob."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    exam_id: str
    exam_title: str
    score: float
    correct: int
    total: int
    passed: bool
    # The threshold this attempt was graded against, so the client draws the line
    # the mark was actually judged by rather than a hardcoded one.
    pass_grade: int
    time_spent_seconds: int
    mode: str
    over_time: bool
    taken_at: ISODateTime


class HistoryOut(HistorySummaryOut):
    """Full record, including the per-question results blob. Returned only for a
    single record — the list endpoint would be a multi-megabyte response."""

    results: Any


class TopicStatOut(BaseModel):
    topic: str
    total: int
    correct: int
    score: int
