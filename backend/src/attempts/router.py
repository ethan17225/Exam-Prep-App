from typing import Annotated

from fastapi import APIRouter, Query, status

from src.attempts import service
from src.attempts.exceptions import NoValidQuestions, RecordNotFound
from src.attempts.schemas import (
    DeletedOut,
    ExamSubmission,
    HistoryOut,
    HistorySummaryOut,
    InProgressOut,
    SaveProgressPayload,
    TopicStatOut,
)
from src.auth.dependencies import CurrentUserDep
from src.database import SessionDep
from src.exams import service as exams_service
from src.exams.exceptions import ExamNotFound

# Submit is addressed under /api/exams but writes History, so it lives here with
# the rest of the attempt lifecycle.
submit_router = APIRouter(prefix="/api/exams", tags=["attempts"])
progress_router = APIRouter(prefix="/api/in-progress", tags=["attempts"])
history_router = APIRouter(prefix="/api/history", tags=["attempts"])

NO_RECORD = {status.HTTP_404_NOT_FOUND: {"description": RecordNotFound.DETAIL}}


@submit_router.post(
    "/{exam_id}/submit",
    response_model=HistoryOut,
    summary="Submit an exam",
    description="Grades the submission, stores a history record and returns it in full.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": NoValidQuestions.DETAIL},
        status.HTTP_404_NOT_FOUND: {"description": ExamNotFound.DETAIL},
    },
)
async def submit_exam(exam_id: str, submission: ExamSubmission, user: CurrentUserDep, db: SessionDep):
    exam = await exams_service.get_visible_exam_or_404(exam_id, user, db, with_questions=True)
    return await service.submit(exam, submission, user, db)


@progress_router.post(
    "",
    response_model=InProgressOut,
    summary="Save exam progress",
    description=("Upserts the caller's autosave for this exam and mode. Safe to call concurrently from multiple tabs."),
    responses={status.HTTP_404_NOT_FOUND: {"description": ExamNotFound.DETAIL}},
)
async def save_progress(payload: SaveProgressPayload, user: CurrentUserDep, db: SessionDep):
    exam = await exams_service.get_visible_exam_or_404(payload.exam_id, user, db)
    return await service.save_progress(payload, exam, user, db)


@progress_router.get(
    "",
    response_model=list[InProgressOut],
    summary="List in-progress attempts",
    description="The caller's own unfinished attempts, most recently saved first.",
)
async def list_in_progress(user: CurrentUserDep, db: SessionDep):
    return await service.list_in_progress(user, db)


# Declared before /{record_id} so the fixed path is not captured as an id.
@progress_router.delete(
    "/by-exam/{exam_id}",
    response_model=DeletedOut,
    summary="Discard progress for an exam",
    description="Deletes the caller's autosave for this exam and mode. Idempotent.",
)
async def delete_in_progress_by_exam(exam_id: str, user: CurrentUserDep, db: SessionDep, mode: str = "exam"):
    await service.delete_in_progress_by_exam(exam_id, mode, user, db)
    return {"deleted": True}


@progress_router.get(
    "/{record_id}",
    response_model=InProgressOut,
    summary="Get an in-progress attempt",
    description="Used to resume an exam. Only the caller's own records are visible.",
    responses=NO_RECORD,
)
async def get_in_progress(record_id: str, user: CurrentUserDep, db: SessionDep):
    record = await service.get_in_progress_or_404(record_id, user, db)
    return service.in_progress_to_dict(record)


@progress_router.delete(
    "/{record_id}",
    response_model=DeletedOut,
    summary="Discard an in-progress attempt",
    description="Deletes one of the caller's saved attempts by id.",
    responses=NO_RECORD,
)
async def delete_in_progress(record_id: str, user: CurrentUserDep, db: SessionDep):
    await service.delete_in_progress(record_id, user, db)
    return {"deleted": True}


@history_router.get(
    "",
    response_model=list[HistorySummaryOut],
    summary="List past attempts",
    description=(
        "Summaries only — the per-question `results` blob is returned by the "
        "single-record endpoint, because listing it is a multi-megabyte response."
    ),
)
async def get_history(
    user: CurrentUserDep,
    db: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_history(user, limit, offset, db)


# Declared before /{record_id}: otherwise "topic-stats" is read as a record id
# and this returns a silent 404 that shows up as an empty overview chart.
@history_router.get(
    "/topic-stats",
    response_model=list[TopicStatOut],
    summary="Per-topic performance",
    description="Correct/total per topic across every attempt, aggregated in the database.",
)
async def get_topic_stats(user: CurrentUserDep, db: SessionDep):
    return await service.topic_stats(user, db)


@history_router.get(
    "/{record_id}",
    response_model=HistoryOut,
    summary="Get a past attempt",
    description="The full record including every question, answer and rationale.",
    responses=NO_RECORD,
)
async def get_history_record(record_id: str, user: CurrentUserDep, db: SessionDep):
    record = await service.get_history_or_404(record_id, user, db)
    return service.history_to_dict(record)


@history_router.delete(
    "/{record_id}",
    response_model=DeletedOut,
    summary="Delete a past attempt",
    description="Removes one of the caller's history records.",
    responses=NO_RECORD,
)
async def delete_history_record(record_id: str, user: CurrentUserDep, db: SessionDep):
    await service.delete_history(record_id, user, db)
    return {"deleted": True}
