from fastapi import APIRouter, status

from src.auth.dependencies import InstructorDep
from src.banks import service
from src.banks.exceptions import (
    BankInUse,
    BankNotFound,
    EmptyBankTitle,
    EmptySectionName,
    SectionNotFound,
)
from src.banks.schemas import (
    BankCreate,
    BankDetailOut,
    BankSectionCreatedOut,
    BankSummaryOut,
    BankUpdate,
    QuestionsAddedOut,
    SectionCreate,
    SectionQuestionsIn,
    SectionUpdate,
)
from src.courses.exceptions import CourseNotFound
from src.database import SessionDep
from src.exams import service as exams_service
from src.exams.exceptions import QuestionNotFound
from src.exams.schemas import QuestionOut, QuestionUpdate
from src.schemas import DeletedOut

router = APIRouter(prefix="/api/question-banks", tags=["question-banks"])

NO_BANK = {status.HTTP_404_NOT_FOUND: {"description": BankNotFound.DETAIL}}
NO_SECTION = {status.HTTP_404_NOT_FOUND: {"description": SectionNotFound.DETAIL}}
NO_QUESTION = {status.HTTP_404_NOT_FOUND: {"description": QuestionNotFound.DETAIL}}
BAD_TITLE = {status.HTTP_400_BAD_REQUEST: {"description": EmptyBankTitle.DETAIL}}
BAD_NAME = {status.HTTP_400_BAD_REQUEST: {"description": EmptySectionName.DETAIL}}


@router.get(
    "",
    response_model=list[BankSummaryOut],
    summary="List my question banks",
    description="Banks the caller owns or has been invited to edit. Students never see this list.",
)
async def list_banks(user: InstructorDep, db: SessionDep):
    return await service.list_mine(user, db)


@router.post(
    "",
    response_model=BankSummaryOut,
    summary="Create a question bank",
    description="Creates an empty bank owned by the caller. Add named sections next.",
    responses={**BAD_TITLE, status.HTTP_404_NOT_FOUND: {"description": CourseNotFound.DETAIL}},
)
async def create_bank(payload: BankCreate, user: InstructorDep, db: SessionDep):
    bank = await service.create(payload, user, db)
    return {
        "id": bank.id,
        "title": bank.title,
        "course_id": bank.course_id,
        "course_name": None,
        "section_count": 0,
        "question_count": 0,
        "created_at": bank.created_at,
        "is_owner": True,
        "is_collaborator": False,
    }


@router.get(
    "/{bank_id}",
    response_model=BankDetailOut,
    summary="Get a question bank",
    description="Sections in display order, each with its questions (answer key included).",
    responses=NO_BANK,
)
async def get_bank(bank_id: str, user: InstructorDep, db: SessionDep):
    return await service.detail(bank_id, user, db)


@router.patch(
    "/{bank_id}",
    response_model=BankSummaryOut,
    summary="Rename a question bank",
    description="Updates the title and optional course. Does not affect linked exams' titles.",
    responses={
        **NO_BANK,
        **BAD_TITLE,
        status.HTTP_404_NOT_FOUND: {"description": CourseNotFound.DETAIL},
    },
)
async def update_bank(bank_id: str, payload: BankUpdate, user: InstructorDep, db: SessionDep):
    await service.update(bank_id, payload, user, db)
    summaries = await service.list_mine(user, db)
    return next(row for row in summaries if row["id"] == bank_id)


@router.delete(
    "/{bank_id}",
    response_model=DeletedOut,
    summary="Delete a question bank",
    description="Refused while any exam is still linked to this bank. Questions and images go with it.",
    responses={**NO_BANK, status.HTTP_409_CONFLICT: {"description": BankInUse.DETAIL}},
)
async def delete_bank(bank_id: str, user: InstructorDep, db: SessionDep):
    await service.get_owned_or_404(bank_id, user, db)
    if await exams_service.bank_has_exams(bank_id, db):
        raise BankInUse()
    images = await exams_service.image_urls_for_bank(bank_id, db)
    await service.delete_bank(bank_id, user, db)
    await exams_service.remove_images(images)
    return {"deleted": True}


@router.post(
    "/{bank_id}/sections",
    response_model=BankSectionCreatedOut,
    summary="Add a section",
    description="Appends a named section. Position is the next integer; drag-reorder is out of scope.",
    responses={**NO_BANK, **BAD_NAME},
)
async def add_section(bank_id: str, payload: SectionCreate, user: InstructorDep, db: SessionDep):
    return await service.add_section(bank_id, payload, user, db)


@router.patch(
    "/{bank_id}/sections/{section_id}",
    response_model=BankSectionCreatedOut,
    summary="Rename a section",
    description="Changes the section's display name. Linked exam shares keep the same section id.",
    responses={**NO_SECTION, **BAD_NAME},
)
async def rename_section(bank_id: str, section_id: str, payload: SectionUpdate, user: InstructorDep, db: SessionDep):
    return await service.rename_section(bank_id, section_id, payload, user, db)


@router.delete(
    "/{bank_id}/sections/{section_id}",
    response_model=DeletedOut,
    summary="Delete a section",
    description="Removes the section and its questions (cascade). Exam shares for it are dropped too.",
    responses=NO_SECTION,
)
async def delete_section(bank_id: str, section_id: str, user: InstructorDep, db: SessionDep):
    await service.get_writable_section_or_404(bank_id, section_id, user, db)
    images = await exams_service.image_urls_for_section(section_id, db)
    await service.delete_section(bank_id, section_id, user, db)
    await exams_service.remove_images(images)
    return {"deleted": True}


@router.post(
    "/{bank_id}/sections/{section_id}/questions",
    response_model=QuestionsAddedOut,
    summary="Add questions to a section",
    description="Accepts `{questions: [...]}` — one item for a manual add, many for a JSON paste.",
    responses=NO_SECTION,
)
async def add_section_questions(
    bank_id: str,
    section_id: str,
    payload: SectionQuestionsIn,
    user: InstructorDep,
    db: SessionDep,
):
    added = await exams_service.add_questions_to_section(bank_id, section_id, payload.questions, user, db)
    return {"added": added}


@router.patch(
    "/{bank_id}/sections/{section_id}/questions/{question_id}",
    response_model=QuestionOut,
    summary="Update a bank question",
    description="Partial update. Only fields present in the request body are changed.",
    responses=NO_QUESTION,
)
async def update_section_question(
    bank_id: str,
    section_id: str,
    question_id: int,
    payload: QuestionUpdate,
    user: InstructorDep,
    db: SessionDep,
):
    return await exams_service.update_section_question(bank_id, section_id, question_id, payload, user, db)


@router.delete(
    "/{bank_id}/sections/{section_id}/questions/{question_id}",
    response_model=DeletedOut,
    summary="Delete a bank question",
    description="Removes the question and its uploaded image, if any.",
    responses=NO_QUESTION,
)
async def delete_section_question(bank_id: str, section_id: str, question_id: int, user: InstructorDep, db: SessionDep):
    await exams_service.delete_section_question(bank_id, section_id, question_id, user, db)
    return {"deleted": True}
