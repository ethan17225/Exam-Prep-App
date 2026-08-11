import pathlib
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from src.attempts import service as attempts_service
from src.auth.dependencies import CurrentUserDep
from src.courses.exceptions import CourseNotFound
from src.database import SessionDep
from src.exams import service, utils
from src.exams.config import exams_settings
from src.exams.constants import ALLOWED_IMAGE_EXTENSIONS
from src.exams.exceptions import (
    EmptyTitle,
    ExamNotFound,
    ExamNotOwned,
    ImageTooLarge,
    QuestionNotFound,
    UnsupportedImageType,
)
from src.exams.schemas import (
    DeletedOut,
    ExamCreate,
    ExamCreatedOut,
    ExamDetailOut,
    ExamSummaryOut,
    ExamTimeLimitUpdate,
    ExamTitleUpdate,
    ImageOut,
    QuestionIn,
    QuestionOut,
    QuestionUpdate,
)

router = APIRouter(prefix="/api/exams", tags=["exams"])
# The two image routes are addressed by bare question id, so they sit outside the
# /api/exams prefix. Same domain, second router.
questions_router = APIRouter(prefix="/api/questions", tags=["questions"])

NOT_OWNER = {status.HTTP_403_FORBIDDEN: {"description": ExamNotOwned.DETAIL}}
NO_EXAM = {status.HTTP_404_NOT_FOUND: {"description": ExamNotFound.DETAIL}}


@router.post(
    "",
    response_model=ExamCreatedOut,
    summary="Create an exam",
    description=(
        "Creates an exam owned by the caller, with all of its questions. "
        "Instructor-created exams are visible to everyone; student-created ones "
        "are private."
    ),
    responses={status.HTTP_404_NOT_FOUND: {"description": CourseNotFound.DETAIL}},
)
async def create_exam(payload: ExamCreate, user: CurrentUserDep, db: SessionDep):
    return await service.create(payload, user, db)


@router.get(
    "",
    response_model=list[ExamSummaryOut],
    summary="List exams",
    description="Exams shared by an instructor plus the caller's own, with question-type counts.",
)
async def list_exams(user: CurrentUserDep, db: SessionDep, course_id: Annotated[str | None, Query()] = None):
    return await service.list_summaries(user, course_id, db)


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
    responses={**NO_EXAM, **NOT_OWNER, status.HTTP_400_BAD_REQUEST: {"description": EmptyTitle.DETAIL}},
)
async def update_exam_title(exam_id: str, payload: ExamTitleUpdate, user: CurrentUserDep, db: SessionDep):
    exam = await service.get_owned_exam_or_404(exam_id, user, db)

    new_title = payload.title.strip()
    if not new_title:
        raise EmptyTitle()

    exam.title = new_title
    # The one import that points "up" the layering: attempts owns the
    # denormalized exam_title copies. Hoisted into the router so that
    # exams.service never imports attempts.service, which would cycle.
    await attempts_service.rename_exam(exam_id, new_title, db)
    await db.commit()
    await db.refresh(exam)
    return await service.exam_summary(exam, db)


@router.patch(
    "/{exam_id}/time-limit",
    response_model=ExamSummaryOut,
    summary="Set the time limit",
    description="Sets or clears the exam's time limit in minutes. Zero or null clears it.",
    responses={**NO_EXAM, **NOT_OWNER},
)
async def update_exam_time_limit(exam_id: str, payload: ExamTimeLimitUpdate, user: CurrentUserDep, db: SessionDep):
    exam = await service.get_owned_exam_or_404(exam_id, user, db)
    limit = payload.time_limit_minutes
    if limit is not None and limit <= 0:
        limit = None
    exam.time_limit_minutes = limit
    await db.commit()
    await db.refresh(exam)
    return await service.exam_summary(exam, db)


@router.delete(
    "/{exam_id}",
    response_model=DeletedOut,
    summary="Delete an exam",
    description=(
        "Deletes the exam, its questions and every in-progress attempt against it. History rows survive by design."
    ),
    responses={**NO_EXAM, **NOT_OWNER},
)
async def delete_exam(exam_id: str, user: CurrentUserDep, db: SessionDep):
    exam = await service.get_owned_exam_or_404(exam_id, user, db)
    # Questions cascade, but their image files do not — reclaim them first.
    images = await service.image_urls_for_exam(exam_id, db)
    await run_in_threadpool(utils.remove_image_files, images)
    await db.delete(exam)
    await db.commit()
    return {"deleted": True}


# ── Question CRUD (exam editor) ───────────────────────────────────


@router.post(
    "/{exam_id}/questions",
    response_model=QuestionOut,
    summary="Add a question",
    description="Appends a question to the exam. Omit `number` to append at the end.",
    responses={**NO_EXAM, **NOT_OWNER},
)
async def add_question(exam_id: str, payload: QuestionIn, user: CurrentUserDep, db: SessionDep):
    await service.get_owned_exam_or_404(exam_id, user, db)
    return await service.add_question(exam_id, payload, db)


@router.patch(
    "/{exam_id}/questions/{question_id}",
    response_model=QuestionOut,
    summary="Update a question",
    description="Partial update. Only fields present in the request body are changed.",
    responses={
        **NOT_OWNER,
        status.HTTP_404_NOT_FOUND: {"description": QuestionNotFound.DETAIL},
    },
)
async def update_question(
    exam_id: str, question_id: int, payload: QuestionUpdate, user: CurrentUserDep, db: SessionDep
):
    await service.get_owned_exam_or_404(exam_id, user, db)
    q = await service.get_question_in_exam_or_404(exam_id, question_id, db)

    # model_fields_set distinguishes "absent" from "explicitly null".
    fields = payload.model_fields_set
    if "number" in fields and payload.number is not None:
        q.number = payload.number
    if "topic" in fields and payload.topic is not None:
        q.topic = payload.topic
    if "type" in fields and payload.type is not None:
        q.type = payload.type
    if "question" in fields and payload.question is not None:
        q.question = payload.question
    if "sections" in fields:
        q.sections = payload.sections
    if "options" in fields:
        q.options = payload.options
    if "answer" in fields:
        q.answer = payload.answer
    if "rationale" in fields and payload.rationale is not None:
        q.rationale = payload.rationale

    await db.commit()
    await db.refresh(q)
    return q


@router.delete(
    "/{exam_id}/questions/{question_id}",
    response_model=DeletedOut,
    summary="Delete a question",
    description="Removes the question and its uploaded image, if any.",
    responses={
        **NOT_OWNER,
        status.HTTP_404_NOT_FOUND: {"description": QuestionNotFound.DETAIL},
    },
)
async def delete_question(exam_id: str, question_id: int, user: CurrentUserDep, db: SessionDep):
    await service.get_owned_exam_or_404(exam_id, user, db)
    q = await service.get_question_in_exam_or_404(exam_id, question_id, db)
    image = q.image
    await db.delete(q)
    await db.commit()
    await run_in_threadpool(utils.remove_image_file, image)
    return {"deleted": True}


@questions_router.post(
    "/{question_id}/image",
    response_model=ImageOut,
    summary="Upload a question image",
    description=(
        "Replaces the question's image. SVG is rejected because uploads are served from the app's own origin."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": UnsupportedImageType.DETAIL},
        status.HTTP_404_NOT_FOUND: {"description": QuestionNotFound.DETAIL},
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": ImageTooLarge.DETAIL},
    },
)
async def upload_question_image(
    question_id: int, user: CurrentUserDep, db: SessionDep, file: Annotated[UploadFile, File()]
):
    q = await service.get_owned_question_or_404(question_id, user, db)

    ext = pathlib.Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise UnsupportedImageType(
            f"Unsupported image type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}"
        )

    filename = utils.image_filename(question_id, ext)
    dest = exams_settings.uploads_dir / filename
    try:
        # One threadpool hop for the whole streamed write, not one per chunk.
        await run_in_threadpool(utils.save_upload, file.file, dest, exams_settings.max_image_bytes)
    except ValueError as exc:
        raise ImageTooLarge(f"Image exceeds the {exams_settings.max_image_bytes // (1024 * 1024)} MB limit") from exc

    previous = q.image
    q.image = utils.image_url(filename)
    await db.commit()
    await db.refresh(q)
    # Only discard the old file once the new one is safely committed.
    await run_in_threadpool(utils.remove_image_file, previous)
    return {"image": q.image}


@questions_router.delete(
    "/{question_id}/image",
    response_model=ImageOut,
    summary="Delete a question image",
    description="Clears the question's image and removes the file from disk.",
    responses={status.HTTP_404_NOT_FOUND: {"description": QuestionNotFound.DETAIL}},
)
async def delete_question_image(question_id: int, user: CurrentUserDep, db: SessionDep):
    q = await service.get_owned_question_or_404(question_id, user, db)
    image = q.image
    q.image = None
    await db.commit()
    await run_in_threadpool(utils.remove_image_file, image)
    return {"image": None}
