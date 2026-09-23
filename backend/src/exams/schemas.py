from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from src.constants import MAX_INT, MAX_QUESTIONS_PER_EXAM
from src.grading.constants import DEFAULT_PASS_GRADE
from src.identifiers import ID_LENGTH
from src.schemas import ISODateTime

# Every string bound mirrors its column width and every int is bounded by
# Postgres' 32-bit INTEGER. Without these the driver raises and the route 500s,
# where a 422 is correct — and on submit a 500 costs the student their attempt.


def _not_none(value: Any) -> Any:
    # `Question.answer` is NOT NULL, so a literal null in the body would be a
    # driver error (500) rather than a validation failure (422).
    if value is None:
        raise ValueError("must not be null")
    return value


Answer = Annotated[Any, AfterValidator(_not_none)]


class QuestionIn(BaseModel):
    topic: str = Field(max_length=2000)
    # Deliberately `str`, not the QuestionType enum: the documented JSON upload
    # format allows arbitrary type strings and grading normalizes them.
    type: str = Field(max_length=30)
    sections: Any = None
    question: str = Field(max_length=20000)
    options: Any = None
    answer: Answer
    rationale: str = Field(default="", max_length=20000)
    # `image` is deliberately NOT accepted from the client. It is a path into the
    # uploads volume, and every delete path unlinks whatever it points at — so a
    # client-supplied value let anyone delete another user's images by pointing a
    # throwaway question at them. It is set only by the upload route.


class QuestionUpdate(BaseModel):
    topic: str | None = Field(default=None, max_length=2000)
    type: str | None = Field(default=None, max_length=30)
    question: str | None = Field(default=None, max_length=20000)
    sections: Any = None
    options: Any = None
    # Absent is fine (partial update); present-and-null is not.
    answer: Answer = None
    rationale: str | None = Field(default=None, max_length=20000)


class ExamCreate(BaseModel):
    title: str = Field(max_length=255)
    # No min_length: creating an exam with no questions is how the manual editor
    # flow starts, and the client then adds them one at a time.
    questions: list[QuestionIn] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    course_id: str | None = Field(default=None, max_length=ID_LENGTH)
    time_limit_minutes: int | None = Field(default=None, ge=0, le=MAX_INT)
    # None means "derive from my role": instructors create assessments, students
    # create study material.
    allow_practice: bool | None = None
    # Defaulted rather than required so existing API callers keep working; the
    # upload form makes it a required field. 0 is not a pass mark and >100 is
    # unreachable, so both are 422 rather than an exam nobody can pass.
    pass_grade: int = Field(default=DEFAULT_PASS_GRADE, ge=1, le=100)
    # When false, attempts keep insertion order (Question.id) instead of shuffling.
    shuffle: bool = True
    # How many questions a student sits per attempt. None = every question.
    questions_per_attempt: int | None = Field(default=None, ge=1, le=MAX_QUESTIONS_PER_EXAM)


class ExamTitleUpdate(BaseModel):
    title: str = Field(max_length=255)


class ExamTimeLimitUpdate(BaseModel):
    time_limit_minutes: int | None = Field(default=None, ge=0, le=MAX_INT)


class ExamAllowPracticeUpdate(BaseModel):
    allow_practice: bool


class ExamPassGradeUpdate(BaseModel):
    pass_grade: int = Field(ge=1, le=100)


class SectionShareIn(BaseModel):
    section_id: str = Field(max_length=ID_LENGTH)
    percent: int = Field(ge=1, le=100)


class ExamFromBank(BaseModel):
    title: str = Field(max_length=255)
    bank_id: str = Field(max_length=ID_LENGTH)
    shares: list[SectionShareIn] = Field(min_length=1)
    # How many questions a student sits. Percents split this total across sections.
    questions_per_attempt: int = Field(ge=1, le=MAX_QUESTIONS_PER_EXAM)
    course_id: str | None = Field(default=None, max_length=ID_LENGTH)
    time_limit_minutes: int | None = Field(default=None, ge=0, le=MAX_INT)
    pass_grade: int = Field(ge=1, le=100)
    shuffle: bool = True


class ExamSettingsUpdate(BaseModel):
    """Partial update for the edit-portal settings strip. Absent fields are left alone."""

    time_limit_minutes: int | None = Field(default=None, ge=0, le=MAX_INT)
    shuffle: bool | None = None
    questions_per_attempt: int | None = Field(default=None, ge=1, le=MAX_QUESTIONS_PER_EXAM)
    # Explicit clear: PATCH bodies cannot distinguish "absent" from "null" for
    # questions_per_attempt without model_fields_set, which the service reads.
    clear_questions_per_attempt: bool = False
    shares: list[SectionShareIn] | None = None


class ExamCreatedOut(BaseModel):
    exam_id: str
    total_questions: int


class KindCountOut(BaseModel):
    kind: str
    count: int


class ExamSummaryOut(BaseModel):
    """Built by `service.exam_summary` — `course_name` is joined and the counts
    are aggregated, so this is not a straight projection of the row."""

    id: str
    title: str
    course_id: str | None
    course_name: str | None
    time_limit_minutes: int | None
    pass_grade: int
    shuffle: bool
    questions_per_attempt: int | None
    allow_practice: bool
    is_owner: bool
    is_collaborator: bool = False
    total_questions: int
    mcq_count: int
    sata_count: int
    fib_count: int
    other_count: int
    kind_counts: list[KindCountOut]
    created_at: ISODateTime
    # Null on a regular exam. Set when this exam draws from a question bank.
    bank_id: str | None = None


class QuestionOut(BaseModel):
    """Full question, as returned by the exam editor's CRUD routes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
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
    omitted while fields it set to None (sections, options, image) are kept.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    type: str
    question: str
    sections: Any = None
    options: Any = None
    image: str | None = None
    answer: Any = None
    rationale: str | None = None


class SectionShareOut(BaseModel):
    section_id: str
    name: str
    percent: int
    question_count: int


class ExamDetailOut(BaseModel):
    id: str
    title: str
    course_id: str | None
    course_name: str | None
    time_limit_minutes: int | None
    pass_grade: int
    shuffle: bool
    questions_per_attempt: int | None
    # Whether `answer`/`rationale` are present on the questions below. Explicit
    # so the client never infers the answer gate from a missing field.
    answers_included: bool
    allow_practice: bool
    is_owner: bool
    is_collaborator: bool = False
    questions: list[ExamQuestionOut]
    bank_id: str | None = None
    bank_backed: bool = False
    section_shares: list[SectionShareOut] | None = None


class ImageOut(BaseModel):
    image: str | None


class ExamCollaboratorInvite(BaseModel):
    email: str = Field(max_length=255)


class ExamCollaboratorOut(BaseModel):
    user_id: str
    email: str
    display_name: str | None = None
    created_at: ISODateTime


class InstructorSearchHit(BaseModel):
    """One instructor returned by the share-dialog typeahead."""

    id: str
    email: str
    display_name: str | None = None
