from datetime import datetime

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.auth.constants import UserRole
from src.auth.models import User
from src.authz import visible
from src.courses import service as courses_service
from src.exams.exceptions import EmptyTitle, ExamNotFound, ImageTooLarge, QuestionNotFound, UnsupportedImageType
from src.exams.models import Exam, Question
from src.exams.schemas import ExamCreate, ExamQuestionOut, QuestionIn, QuestionUpdate
from src.grading.service import TypeCountRow, question_type_counts
from src.identifiers import new_id
from src.storage import (
    ALLOWED_IMAGE_EXTENSIONS,
    remove_upload_file,
    remove_upload_files,
    save_upload,
    storage_settings,
    upload_filename,
    upload_url,
    validated_extension,
)


def _clean_title(title: str) -> str:
    """One code path for the title rule, so create and rename cannot disagree."""
    cleaned = title.strip()
    if not cleaned:
        raise EmptyTitle()
    return cleaned


# ── Lookups ───────────────────────────────────────────────────────
#
# Not-owned and not-found both raise the same 404. Distinguishing them would
# confirm that an id exists to someone who may not see it.


async def get_visible_exam_or_404(exam_id: str, user: User, db: AsyncSession, with_questions: bool = False) -> Exam:
    """Read access. Deliberately a plain function, not a FastAPI dependency:
    dependencies resolve before the request body is validated, so making this a
    dependency would turn a malformed-payload 422 into a 404."""
    # `course` is eager-loaded unconditionally: every caller ends up rendering
    # course_name, and it is a single row on a many-to-one.
    stmt: Select = select(Exam).options(joinedload(Exam.course)).where(Exam.id == exam_id, visible(Exam, user))
    if with_questions:
        # Otherwise `exam.questions` lazy-loads, which raises under async.
        stmt = stmt.options(selectinload(Exam.questions))
    exam = (await db.execute(stmt)).scalars().unique().one_or_none()
    if not exam:
        raise ExamNotFound()
    return exam


async def get_owned_exam_or_404(exam_id: str, user: User, db: AsyncSession) -> Exam:
    """Write access. Being able to see a shared exam never implies being able to
    change it, so this is separate from the read predicate."""
    stmt = select(Exam).options(joinedload(Exam.course)).where(Exam.id == exam_id, Exam.owner_id == user.id)
    exam = (await db.execute(stmt)).scalars().unique().one_or_none()
    if not exam:
        raise ExamNotFound()
    return exam


async def get_owned_question_or_404(question_id: int, user: User, db: AsyncSession) -> Question:
    """`question.id` is a serial integer and trivially enumerable, so ownership
    is resolved by joining through Exam — in one round trip."""
    stmt = (
        select(Question)
        .join(Exam, Question.exam_id == Exam.id)
        .where(Question.id == question_id, Exam.owner_id == user.id)
    )
    question = (await db.execute(stmt)).scalar_one_or_none()
    if not question:
        raise QuestionNotFound()
    return question


async def get_owned_question_in_exam_or_404(exam_id: str, question_id: int, user: User, db: AsyncSession) -> Question:
    stmt = (
        select(Question)
        .join(Exam, Question.exam_id == Exam.id)
        .where(Question.id == question_id, Question.exam_id == exam_id, Exam.owner_id == user.id)
    )
    question = (await db.execute(stmt)).scalar_one_or_none()
    if not question:
        raise QuestionNotFound()
    return question


# ── Question projections ──────────────────────────────────────────


async def questions_by_exam_ids(exam_ids, db: AsyncSession):
    """Rows needed to grade, batched for many exams at once. Only the columns
    grading reads — the full rows carry JSONB deserialized for nothing."""
    stmt = select(Question.exam_id, Question.number, Question.type, Question.answer, Question.options).where(
        Question.exam_id.in_(exam_ids)
    )
    return (await db.execute(stmt)).all()


async def settings_by_exam_ids(exam_ids, db: AsyncSession) -> dict[str, tuple[int | None, int]]:
    """`(time_limit_minutes, pass_grade)` for many exams at once, keyed by exam id.

    The tracking dashboard needs both: the countdown must be derived from the
    server's clock rather than echoing back the one the student's browser
    reported, and the pass mark is per-exam.
    """
    stmt = select(Exam.id, Exam.time_limit_minutes, Exam.pass_grade).where(Exam.id.in_(exam_ids))
    return {row.id: (row.time_limit_minutes, row.pass_grade) for row in (await db.execute(stmt)).all()}


async def count_owned(user: User, db: AsyncSession) -> int:
    """How many exams this user has published. Read by the instructor overview."""
    return await db.scalar(select(func.count(Exam.id)).where(Exam.owner_id == user.id)) or 0


async def _type_count_rows(exam_ids, db: AsyncSession):
    stmt = select(Question.exam_id, Question.type, Question.options).where(Question.exam_id.in_(exam_ids))
    # Column-tuple select: .scalars() here would silently discard every column
    # but the first.
    return (await db.execute(stmt)).all()


def _summary(exam: Exam, course_name: str | None, counts: list[TypeCountRow], user: User) -> dict:
    """The one place ExamSummaryOut's computed shape is assembled."""
    mcq, sata, fib, other = question_type_counts(counts)
    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": course_name,
        "time_limit_minutes": exam.time_limit_minutes,
        "pass_grade": exam.pass_grade,
        "allow_practice": exam.allow_practice,
        "is_owner": exam.owner_id == user.id,
        "total_questions": len(counts),
        "mcq_count": mcq,
        "sata_count": sata,
        "fib_count": fib,
        "other_count": other,
        "created_at": exam.created_at,
    }


async def exam_summary(exam: Exam, user: User, db: AsyncSession) -> dict:
    counts = [TypeCountRow(qtype, options) for _, qtype, options in await _type_count_rows([exam.id], db)]
    # exam.course is eager-loaded by both loaders, so this costs nothing.
    return _summary(exam, exam.course.name if exam.course else None, counts, user)


async def list_summaries(user: User, course_id: str | None, db: AsyncSession, limit: int = 200) -> list[dict]:
    stmt = select(Exam).options(joinedload(Exam.course)).where(visible(Exam, user))
    if course_id:
        stmt = stmt.where(Exam.course_id == course_id)
    # Bounded: shared exams are visible to everyone, and the count query below
    # pulls every question's options JSONB for each one.
    stmt = stmt.order_by(Exam.created_at).limit(limit)
    exams = list((await db.execute(stmt)).scalars().unique().all())

    counts: dict[str, list[TypeCountRow]] = {e.id: [] for e in exams}
    if counts:
        for exam_id, qtype, options in await _type_count_rows(list(counts), db):
            counts[exam_id].append(TypeCountRow(qtype, options))

    return [_summary(e, e.course.name if e.course else None, counts[e.id], user) for e in exams]


# ── Exam lifecycle ────────────────────────────────────────────────


async def create(payload: ExamCreate, user: User, db: AsyncSession) -> dict:
    title = _clean_title(payload.title)
    if payload.course_id:
        # Validates that the course is visible to the caller; raises CourseNotFound.
        await courses_service.get_visible_or_404(payload.course_id, user, db)

    exam_id = new_id()
    db.add(
        Exam(
            id=exam_id,
            owner_id=user.id,
            is_shared=user.role == UserRole.INSTRUCTOR,
            # Instructor exams default to assessment-only; a student's own exams
            # are study material. Either owner can flip it afterwards.
            allow_practice=(
                payload.allow_practice if payload.allow_practice is not None else user.role != UserRole.INSTRUCTOR
            ),
            title=title,
            course_id=payload.course_id,
            time_limit_minutes=payload.time_limit_minutes,
            pass_grade=payload.pass_grade,
            created_at=datetime.now(),
        )
    )
    for index, q in enumerate(payload.questions, start=1):
        db.add(_new_question(exam_id, q, fallback_number=index))
    await db.commit()
    return {"exam_id": exam_id, "total_questions": len(payload.questions)}


async def detail(exam_id: str, user: User, include_answers: bool, db: AsyncSession) -> dict:
    exam = await get_visible_exam_or_404(exam_id, user, db, with_questions=True)

    # The single gate on answer-key disclosure. An assessment-only exam
    # (allow_practice=False) never yields its key to anyone but the owner, so
    # there is no route by which a student can read it before submitting.
    is_owner = exam.owner_id == user.id
    include_answers = include_answers and (is_owner or exam.allow_practice)

    questions = []
    for q in exam.questions:
        # Derived from the schema rather than by listing the eight fields again.
        # `answer`/`rationale` must be ABSENT (not null) when not requested — the
        # route pairs this with response_model_exclude_unset=True.
        row = ExamQuestionOut.model_validate(q).model_dump(exclude={"answer", "rationale"})
        if include_answers:
            row["answer"] = q.answer
            row["rationale"] = q.rationale or ""
        questions.append(row)

    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": exam.course.name if exam.course else None,
        "time_limit_minutes": exam.time_limit_minutes,
        "pass_grade": exam.pass_grade,
        # Explicit, so the client never has to infer the gate's outcome from
        # whether a field happens to be missing.
        "answers_included": include_answers,
        "allow_practice": exam.allow_practice,
        "is_owner": is_owner,
        "questions": questions,
    }


async def rename(exam_id: str, title: str, user: User, db: AsyncSession) -> Exam:
    """Applies the new title but does NOT commit.

    The denormalized copies in `attempts` must land in the same transaction, and
    that fan-out lives in a domain this one may not import. The router sequences
    the two and `attempts.service.rename_exam` commits both.
    """
    exam = await get_owned_exam_or_404(exam_id, user, db)
    exam.title = _clean_title(title)
    return exam


async def set_allow_practice(exam_id: str, allow: bool, user: User, db: AsyncSession) -> Exam:
    exam = await get_owned_exam_or_404(exam_id, user, db)
    exam.allow_practice = allow
    await db.commit()
    return exam


async def set_pass_grade(exam_id: str, pass_grade: int, user: User, db: AsyncSession) -> Exam:
    """Applies to attempts submitted from now on. Past attempts keep the threshold
    they were graded against — History carries its own copy."""
    exam = await get_owned_exam_or_404(exam_id, user, db)
    exam.pass_grade = pass_grade
    await db.commit()
    return exam


async def set_time_limit(exam_id: str, minutes: int | None, user: User, db: AsyncSession) -> Exam:
    exam = await get_owned_exam_or_404(exam_id, user, db)
    # Zero or negative clears the limit rather than storing a nonsensical one.
    exam.time_limit_minutes = minutes if minutes else None
    await db.commit()
    return exam


async def delete_exam(exam_id: str, user: User, db: AsyncSession) -> None:
    exam = await get_owned_exam_or_404(exam_id, user, db)
    # Read the paths before the cascade removes the rows, but only unlink after
    # the commit succeeds — otherwise a failed commit leaves an exam whose
    # images are already gone.
    images = await _image_urls_for_exam(exam_id, db)
    await db.delete(exam)
    await db.commit()
    await run_in_threadpool(remove_upload_files, images)


async def _image_urls_for_exam(exam_id: str, db: AsyncSession) -> list[str]:
    stmt = select(Question.image).where(Question.exam_id == exam_id)
    # Single column, so .scalars() is correct here.
    return [url for url in (await db.execute(stmt)).scalars().all() if url]


# ── Questions ─────────────────────────────────────────────────────


def _new_question(exam_id: str, payload: QuestionIn, fallback_number: int) -> Question:
    return Question(
        exam_id=exam_id,
        number=payload.number or fallback_number,
        topic=payload.topic,
        type=payload.type,
        question=payload.question,
        sections=payload.sections,
        options=payload.options,
        answer=payload.answer,
        rationale=payload.rationale,
        # image is intentionally absent — see QuestionIn. Only the upload route
        # writes it, so it can never point at a file the caller does not own.
    )


async def add_question(exam_id: str, payload: QuestionIn, user: User, db: AsyncSession) -> Question:
    await get_owned_exam_or_404(exam_id, user, db)
    number = payload.number
    if not number:
        # Scalar query rather than loading the collection just to find a max.
        current = await db.scalar(select(func.max(Question.number)).where(Question.exam_id == exam_id))
        number = (current or 0) + 1
    question = _new_question(exam_id, payload, fallback_number=number)
    db.add(question)
    await db.commit()
    return question


async def update_question(
    exam_id: str, question_id: int, payload: QuestionUpdate, user: User, db: AsyncSession
) -> Question:
    question = await get_owned_question_in_exam_or_404(exam_id, question_id, user, db)

    # model_fields_set distinguishes "absent" from "explicitly null": nullable
    # fields accept an explicit null, the rest only change when given a value.
    nullable = {"sections", "options", "answer"}
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if field in nullable or value is not None:
            setattr(question, field, value)

    await db.commit()
    return question


async def delete_question(exam_id: str, question_id: int, user: User, db: AsyncSession) -> None:
    question = await get_owned_question_in_exam_or_404(exam_id, question_id, user, db)
    image = question.image
    await db.delete(question)
    await db.commit()
    await run_in_threadpool(remove_upload_file, image)


async def replace_question_image(question_id: int, file: UploadFile, user: User, db: AsyncSession) -> Question:
    question = await get_owned_question_or_404(question_id, user, db)

    ext = validated_extension(file.filename)
    if not ext:
        raise UnsupportedImageType(f"Unsupported image type. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}")

    filename = upload_filename(f"q{question_id}", ext)
    dest = storage_settings.dir / filename
    try:
        # One threadpool hop for the whole streamed write, not one per chunk.
        await run_in_threadpool(save_upload, file.file, dest, storage_settings.max_image_bytes)
    except ValueError as exc:
        raise ImageTooLarge(f"Image exceeds the {storage_settings.max_image_bytes // (1024 * 1024)} MB limit") from exc

    previous = question.image
    question.image = upload_url(filename)
    await db.commit()
    # Only discard the old file once the new one is safely committed.
    await run_in_threadpool(remove_upload_file, previous)
    return question


async def clear_question_image(question_id: int, user: User, db: AsyncSession) -> Question:
    question = await get_owned_question_or_404(question_id, user, db)
    image = question.image
    question.image = None
    await db.commit()
    await run_in_threadpool(remove_upload_file, image)
    return question
