from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.constants import MAX_INT, MAX_QUESTIONS_PER_EXAM

# Every string bound mirrors its column width and every int is bounded by
# Postgres' 32-bit INTEGER. Without these the driver raises and the route 500s,
# where a 422 is correct — and on submit a 500 costs the student their attempt.


class QuestionIn(BaseModel):
    number: int = Field(ge=0, le=MAX_INT)
    topic: str = Field(max_length=2000)
    # Deliberately `str`, not the QuestionType enum: the documented JSON upload
    # format allows arbitrary type strings and grading normalizes them.
    type: str = Field(max_length=30)
    sections: Any = None
    question: str = Field(max_length=20000)
    options: Any = None
    answer: Any
    rationale: str = Field(default="", max_length=20000)
    image: str | None = Field(default=None, max_length=500)


class QuestionUpdate(BaseModel):
    number: int | None = Field(default=None, ge=0, le=MAX_INT)
    topic: str | None = Field(default=None, max_length=2000)
    type: str | None = Field(default=None, max_length=30)
    question: str | None = Field(default=None, max_length=20000)
    sections: Any = None
    options: Any = None
    answer: Any = None
    rationale: str | None = Field(default=None, max_length=20000)


class ExamCreate(BaseModel):
    title: str = Field(max_length=255)
    questions: list[QuestionIn] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    course_id: str | None = Field(default=None, max_length=8)
    time_limit_minutes: int | None = Field(default=None, ge=0, le=MAX_INT)


class ExamTitleUpdate(BaseModel):
    title: str = Field(max_length=255)


class ExamTimeLimitUpdate(BaseModel):
    time_limit_minutes: int | None = Field(default=None, ge=0, le=MAX_INT)


class ExamCreatedOut(BaseModel):
    exam_id: str
    total_questions: int


class ExamSummaryOut(BaseModel):
    id: str
    title: str
    course_id: str | None
    course_name: str | None
    time_limit_minutes: int | None
    total_questions: int
    mcq_count: int
    sata_count: int
    fib_count: int
    other_count: int
    created_at: str


class QuestionOut(BaseModel):
    """Full question, as returned by the exam editor's CRUD routes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    topic: str
    type: str
    question: str
    sections: Any = None
    options: Any = None
    answer: Any = None
    rationale: str = ""
    image: str | None = None


class ExamQuestionOut(BaseModel):
    """Question embedded in GET /api/exams/{id}.

    `answer` and `rationale` must be *absent*, not null, when include_answers is
    false — the frontend distinguishes the two. The route pairs this with
    `response_model_exclude_unset=True`, so a field the service never set is
    omitted, while fields it set to None (sections, options, image) are kept.
    """

    id: int
    number: int
    topic: str
    type: str
    question: str
    sections: Any = None
    options: Any = None
    image: str | None = None
    answer: Any = None
    rationale: str | None = None


class ExamDetailOut(BaseModel):
    id: str
    title: str
    course_id: str | None
    course_name: str | None
    time_limit_minutes: int | None
    questions: list[ExamQuestionOut]


class ImageOut(BaseModel):
    image: str | None


class DeletedOut(BaseModel):
    deleted: bool
