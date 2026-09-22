from pydantic import BaseModel, ConfigDict, Field

from src.constants import MAX_QUESTIONS_PER_EXAM
from src.exams.schemas import QuestionIn, QuestionOut
from src.identifiers import ID_LENGTH
from src.schemas import ISODateTime


class BankCreate(BaseModel):
    title: str = Field(max_length=255)
    course_id: str | None = Field(default=None, max_length=ID_LENGTH)


class BankUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    course_id: str | None = Field(default=None, max_length=ID_LENGTH)


class SectionCreate(BaseModel):
    name: str = Field(max_length=255)


class SectionUpdate(BaseModel):
    name: str = Field(max_length=255)


class SectionQuestionsIn(BaseModel):
    questions: list[QuestionIn] = Field(min_length=1, max_length=MAX_QUESTIONS_PER_EXAM)


class BankSummaryOut(BaseModel):
    id: str
    title: str
    course_id: str | None
    course_name: str | None
    section_count: int
    question_count: int
    created_at: ISODateTime
    is_owner: bool = True
    is_collaborator: bool = False


class BankSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    position: int
    question_count: int
    questions: list[QuestionOut]


class BankDetailOut(BaseModel):
    id: str
    title: str
    course_id: str | None
    course_name: str | None
    created_at: ISODateTime
    is_owner: bool = True
    is_collaborator: bool = False
    sections: list[BankSectionOut]


class QuestionsAddedOut(BaseModel):
    added: int


class BankSectionCreatedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    position: int
