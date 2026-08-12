from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status

from src.attempts import service as attempts_service
from src.auth.dependencies import CurrentUserDep
from src.courses.exceptions import CourseNotFound
from src.database import SessionDep
from src.exams import service
from src.exams.exceptions import EmptyTitle, ExamNotFound, ImageTooLarge, QuestionNotFound, UnsupportedImageType
from src.exams.schemas import (
    ExamAllowPracticeUpdate,
    ExamCreate,
    ExamCreatedOut,
    ExamDetailOut,
    ExamPassGradeUpdate,
    ExamSummaryOut,
    ExamTimeLimitUpdate,
    ExamTitleUpdate,
    ImageOut,
    QuestionIn,
    QuestionOut,
    QuestionUpdate,
)
from src.schemas import DeletedOut

router = APIRouter(prefix="/api/exams", tags=["exams"])
# The two image routes are addressed by bare question id, so they sit outside the
# /api/exams prefix. Same domain, second router.
questions_router = APIRouter(prefix="/api/questions", tags=["questions"])

# Not-owned and not-found are the same 404 — see exams.service.
NO_EXAM = {status.HTTP_404_NOT_FOUND: {"description": ExamNotFound.DETAIL}}
NO_QUESTION = {status.HTTP_404_NOT_FOUND: {"description": QuestionNotFound.DETAIL}}
BAD_TITLE = {status.HTTP_400_BAD_REQUEST: {"description": EmptyTitle.DETAIL}}


@router.post(
    "",
    response_model=ExamCreatedOut,
    summary="Create an exam",
    description=(
        "Creates an exam owned by the caller, with all of its questions. "
        "Instructor-created exams are visible to everyone; student-created ones "
        "are private."
    ),
    responses={**BAD_TITLE, status.HTTP_404_NOT_FOUND: {"description": CourseNotFound.DETAIL}},
)
async def create_exam(payload: ExamCreate, user: CurrentUserDep, db: SessionDep):
    return await service.create(payload, user, db)


@router.get(
    "",
    response_model=list[ExamSummaryOut],
    summary="List exams",
    description="Exams shared by an instructor plus the caller's own, with question-type counts.",
)
async def list_exams(
    user: CurrentUserDep,
    db: SessionDep,
    course_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    return await service.list_summaries(user, course_id, db, limit)


@router.get(
    "/{exam_id}",
    response_model=ExamDetailOut,
    # `answer` and `rationale` must be absent, not null, when include_answers is
    # false — the frontend distinguishes the two.
    response_model_exclude_unset=True,
    summary="Get an exam",
    description=(
        "Returns the exam and its questions. `include_answers` adds the answer "
        "key and rationale, which the practice-mode client needs to grade locally."
    ),
    responses=NO_EXAM,
)
async def get_exam(exam_id: str, user: CurrentUserDep, db: SessionDep, include_answers: bool = False):
    return await service.detail(exam_id, user, include_answers, db)


@router.patch(
    "/{exam_id}",
    response_model=ExamSummaryOut,
    summary="Rename an exam",
    description="Renames the exam and fans the new title out to every saved attempt.",
    responses={**NO_EXAM, **BAD_TITLE},
)
async def update_exam_title(exam_id: str, payload: ExamTitleUpdate, user: CurrentUserDep, db: SessionDep):
    exam = await service.rename(exam_id, payload.title, user, db)
    # The one import that points "up" the layering: attempts owns the
    # denormalized exam_title copies. Hoisted into the router so that
    # exams.service never imports attempts.service, which would cycle. It
    # commits the rename staged above, so both land in one transaction.
    await attempts_service.rename_exam(exam_id, exam.title, db)
    return await service.exam_summary(exam, user, db)


@router.patch(
    "/{exam_id}/time-limit",
    response_model=ExamSummaryOut,
    summary="Set the time limit",
    description="Sets or clears the exam's time limit in minutes. Zero or null clears it.",
    responses=NO_EXAM,
)
async def update_exam_time_limit(exam_id: str, payload: ExamTimeLimitUpdate, user: CurrentUserDep, db: SessionDep):
    exam = await service.set_time_limit(exam_id, payload.time_limit_minutes, user, db)
    return await service.exam_summary(exam, user, db)


@router.patch(
    "/{exam_id}/allow-practice",
    response_model=ExamSummaryOut,
    summary="Allow or forbid practice mode",
    description=(
        "Practice mode reveals the answer key, so an exam used for grading must "
        "have this off. Turning it off also disables flashcards and rejects "
        "in-flight practice attempts."
    ),
    responses=NO_EXAM,
)
async def update_allow_practice(exam_id: str, payload: ExamAllowPracticeUpdate, user: CurrentUserDep, db: SessionDep):
    exam = await service.set_allow_practice(exam_id, payload.allow_practice, user, db)
    return await service.exam_summary(exam, user, db)


@router.patch(
    "/{exam_id}/pass-grade",
    response_model=ExamSummaryOut,
    summary="Set the pass grade",
    description=(
        "Sets the passing score as a percentage, 1-100. Applies to attempts "
        "submitted from now on: every past attempt keeps the threshold it was "
        "actually graded against."
    ),
    responses=NO_EXAM,
)
async def update_exam_pass_grade(exam_id: str, payload: ExamPassGradeUpdate, user: CurrentUserDep, db: SessionDep):
    exam = await service.set_pass_grade(exam_id, payload.pass_grade, user, db)
    return await service.exam_summary(exam, user, db)


@router.delete(
    "/{exam_id}",
    response_model=DeletedOut,
    summary="Delete an exam",
    description=(
        "Deletes the exam, its questions and every in-progress attempt against it. History rows survive by design."
    ),
    responses=NO_EXAM,
)
async def delete_exam(exam_id: str, user: CurrentUserDep, db: SessionDep):
    await service.delete_exam(exam_id, user, db)
    return {"deleted": True}


# ── Question CRUD (exam editor) ───────────────────────────────────


@router.post(
    "/{exam_id}/questions",
    response_model=QuestionOut,
    summary="Add a question",
    description="Appends a question to the exam. Omit `number` to append at the end.",
    responses=NO_EXAM,
)
async def add_question(exam_id: str, payload: QuestionIn, user: CurrentUserDep, db: SessionDep):
    return await service.add_question(exam_id, payload, user, db)


@router.patch(
    "/{exam_id}/questions/{question_id}",
    response_model=QuestionOut,
    summary="Update a question",
    description="Partial update. Only fields present in the request body are changed.",
    responses=NO_QUESTION,
)
async def update_question(
    exam_id: str, question_id: int, payload: QuestionUpdate, user: CurrentUserDep, db: SessionDep
):
    return await service.update_question(exam_id, question_id, payload, user, db)


@router.delete(
    "/{exam_id}/questions/{question_id}",
    response_model=DeletedOut,
    summary="Delete a question",
    description="Removes the question and its uploaded image, if any.",
    responses=NO_QUESTION,
)
async def delete_question(exam_id: str, question_id: int, user: CurrentUserDep, db: SessionDep):
    await service.delete_question(exam_id, question_id, user, db)
    return {"deleted": True}


@questions_router.post(
    "/{question_id}/image",
    response_model=ImageOut,
    summary="Upload a question image",
    description=(
        "Replaces the question's image. SVG is rejected because uploads are served from the app's own origin."
    ),
    responses={
        **NO_QUESTION,
        status.HTTP_400_BAD_REQUEST: {"description": UnsupportedImageType.DETAIL},
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": ImageTooLarge.DETAIL},
    },
)
async def upload_question_image(
    question_id: int, user: CurrentUserDep, db: SessionDep, file: Annotated[UploadFile, File()]
):
    return await service.replace_question_image(question_id, file, user, db)


@questions_router.delete(
    "/{question_id}/image",
    response_model=ImageOut,
    summary="Delete a question image",
    description="Clears the question's image and removes the file from disk.",
    responses=NO_QUESTION,
)
async def delete_question_image(question_id: int, user: CurrentUserDep, db: SessionDep):
    return await service.clear_question_image(question_id, user, db)
