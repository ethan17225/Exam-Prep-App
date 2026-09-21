import random
from datetime import datetime

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.auth.constants import STAFF_ROLES
from src.auth.models import User
from src.authz import visible
from src.banks import service as banks_service
from src.banks.exceptions import DuplicateSectionShare, EmptyBankDraw, SectionNotFound
from src.banks.models import BankSection, QuestionBank
from src.courses import service as courses_service
from src.exams.exceptions import (
    AttemptLargerThanBank,
    EmptyTitle,
    ExamNotFound,
    ImageTooLarge,
    QuestionNotFound,
    UnsupportedImageType,
)
from src.exams.models import Exam, ExamSectionShare, Question
from src.exams.schemas import ExamCreate, ExamFromBank, ExamQuestionOut, QuestionIn, QuestionUpdate, SectionShareIn
from src.grading.service import GradableRow, TypeCountRow, question_kind_counts, question_type_counts
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
    is resolved by joining through Exam or BankSection→QuestionBank — in one
    round trip. A question belongs to exactly one of those parents."""
    stmt = (
        select(Question)
        .outerjoin(Exam, Question.exam_id == Exam.id)
        .outerjoin(BankSection, Question.section_id == BankSection.id)
        .outerjoin(QuestionBank, BankSection.bank_id == QuestionBank.id)
        .where(
            Question.id == question_id,
            or_(Exam.owner_id == user.id, QuestionBank.owner_id == user.id),
        )
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
    grading reads — the full rows carry JSONB deserialized for nothing.

    Bank-backed exams store questions on sections, not `exam_id`, so callers
    that need those should use `gradable_by_ids` instead.
    """
    stmt = select(Question.exam_id, Question.id, Question.type, Question.answer, Question.options).where(
        Question.exam_id.in_(exam_ids)
    )
    return (await db.execute(stmt)).all()


async def gradable_by_ids(ids, db: AsyncSession) -> dict[int, GradableRow]:
    """Answer-key rows keyed by question id, for live grading of a mixed paper."""
    if not ids:
        return {}
    stmt = select(Question.id, Question.type, Question.answer, Question.options).where(Question.id.in_(ids))
    return {row.id: GradableRow(row.type, row.answer, row.options) for row in (await db.execute(stmt)).all()}


async def questions_in_order(ids: list[int], db: AsyncSession) -> list[Question]:
    """Load questions by id, preserving `ids` order and dropping any that were deleted."""
    if not ids:
        return []
    rows = list((await db.execute(select(Question).where(Question.id.in_(ids)))).scalars().all())
    by_id = {q.id: q for q in rows}
    return [by_id[qid] for qid in ids if qid in by_id]


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
    if not exam_ids:
        return []
    stmt = select(Question.exam_id, Question.type, Question.options).where(Question.exam_id.in_(exam_ids))
    # Column-tuple select: .scalars() here would silently discard every column
    # but the first.
    direct = list((await db.execute(stmt)).all())
    via_bank = list(
        (
            await db.execute(
                select(ExamSectionShare.exam_id, Question.type, Question.options)
                .join(Question, Question.section_id == ExamSectionShare.section_id)
                .where(ExamSectionShare.exam_id.in_(exam_ids))
            )
        ).all()
    )
    return direct + via_bank


async def _bank_expected_draws(exam_ids, db: AsyncSession) -> dict[str, int]:
    """How many questions a student sits, from the exam length and section mix."""
    if not exam_ids:
        return {}
    totals = dict((await db.execute(select(Exam.id, Exam.questions_per_attempt).where(Exam.id.in_(exam_ids)))).all())
    rows = (
        await db.execute(
            select(ExamSectionShare.exam_id, ExamSectionShare.percent, func.count(Question.id))
            .select_from(ExamSectionShare)
            .outerjoin(Question, Question.section_id == ExamSectionShare.section_id)
            .where(ExamSectionShare.exam_id.in_(exam_ids))
            .group_by(ExamSectionShare.exam_id, ExamSectionShare.section_id, ExamSectionShare.percent)
        )
    ).all()
    grouped: dict[str, list[tuple[int, int]]] = {eid: [] for eid in exam_ids}
    for exam_id, percent, size in rows:
        grouped[exam_id].append((percent, size))
    draws: dict[str, int] = {}
    for exam_id, parts in grouped.items():
        percents = [p for p, _ in parts]
        sizes = [s for _, s in parts]
        draws[exam_id] = sum(allocate_section_draws(totals.get(exam_id), sizes, percents))
    return draws


def _summary(
    exam: Exam,
    course_name: str | None,
    counts: list[TypeCountRow],
    user: User,
    total_questions: int | None = None,
) -> dict:
    """The one place ExamSummaryOut's computed shape is assembled."""
    mcq, sata, fib, other = question_type_counts(counts)
    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": course_name,
        "time_limit_minutes": exam.time_limit_minutes,
        "pass_grade": exam.pass_grade,
        "shuffle": exam.shuffle,
        "questions_per_attempt": exam.questions_per_attempt,
        "allow_practice": exam.allow_practice,
        "is_owner": exam.owner_id == user.id,
        "total_questions": len(counts) if total_questions is None else total_questions,
        "mcq_count": mcq,
        "sata_count": sata,
        "fib_count": fib,
        "other_count": other,
        "kind_counts": question_kind_counts(counts),
        "created_at": exam.created_at,
        "bank_id": exam.bank_id,
    }


async def exam_summary(exam: Exam, user: User, db: AsyncSession) -> dict:
    counts = [TypeCountRow(qtype, options) for _, qtype, options in await _type_count_rows([exam.id], db)]
    total = None
    if exam.bank_id:
        total = (await _bank_expected_draws([exam.id], db)).get(exam.id, 0)
    # exam.course is eager-loaded by both loaders, so this costs nothing.
    return _summary(exam, exam.course.name if exam.course else None, counts, user, total)


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

    bank_ids = [e.id for e in exams if e.bank_id]
    draws = await _bank_expected_draws(bank_ids, db) if bank_ids else {}
    return [
        _summary(
            e,
            e.course.name if e.course else None,
            counts[e.id],
            user,
            draws.get(e.id, 0) if e.bank_id else None,
        )
        for e in exams
    ]


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
            is_shared=user.role in STAFF_ROLES,
            # Instructor exams default to assessment-only; a student's own exams
            # are study material. Either owner can flip it afterwards.
            allow_practice=(
                payload.allow_practice if payload.allow_practice is not None else user.role not in STAFF_ROLES
            ),
            title=title,
            course_id=payload.course_id,
            time_limit_minutes=payload.time_limit_minutes,
            pass_grade=payload.pass_grade,
            shuffle=payload.shuffle,
            questions_per_attempt=payload.questions_per_attempt,
            created_at=datetime.now(),
        )
    )
    for q in payload.questions:
        db.add(_new_question(exam_id, q))
    await db.commit()
    return {"exam_id": exam_id, "total_questions": len(payload.questions)}


async def create_from_bank(payload: ExamFromBank, user: User, db: AsyncSession) -> dict:
    title = _clean_title(payload.title)
    bank = await banks_service.get_owned_or_404(payload.bank_id, user, db)
    if payload.course_id:
        await courses_service.get_visible_or_404(payload.course_id, user, db)
    await _validate_shares(payload.shares, {s.id for s in bank.sections}, db, payload.questions_per_attempt)

    exam_id = new_id()
    db.add(
        Exam(
            id=exam_id,
            owner_id=user.id,
            is_shared=user.role == UserRole.INSTRUCTOR,
            allow_practice=user.role != UserRole.INSTRUCTOR,
            title=title,
            course_id=payload.course_id,
            time_limit_minutes=payload.time_limit_minutes,
            pass_grade=payload.pass_grade,
            shuffle=payload.shuffle,
            questions_per_attempt=payload.questions_per_attempt,
            bank_id=payload.bank_id,
            created_at=datetime.now(),
        )
    )
    for share in payload.shares:
        db.add(ExamSectionShare(exam_id=exam_id, section_id=share.section_id, percent=share.percent))
    await db.commit()
    expected = (await _bank_expected_draws([exam_id], db)).get(exam_id, 0)
    return {"exam_id": exam_id, "total_questions": expected}


async def detail(
    exam_id: str,
    user: User,
    include_answers: bool,
    db: AsyncSession,
    question_order: list[int] | None = None,
) -> dict:
    exam = await get_visible_exam_or_404(exam_id, user, db, with_questions=True)

    # The single gate on answer-key disclosure. An assessment-only exam
    # (allow_practice=False) never yields its key to anyone but the owner, so
    # there is no route by which a student can read it before submitting.
    is_owner = exam.owner_id == user.id
    include_answers = include_answers and (is_owner or exam.allow_practice)
    bank_backed = exam.bank_id is not None

    if bank_backed:
        if question_order:
            source = await questions_in_order(question_order, db)
        elif include_answers:
            source = await bank_pool_questions(exam.id, db)
        else:
            source = []
    else:
        source = exam.questions

    questions = []
    for q in source:
        # Derived from the schema rather than by listing the eight fields again.
        # `answer`/`rationale` must be ABSENT (not null) when not requested — the
        # route pairs this with response_model_exclude_unset=True.
        row = ExamQuestionOut.model_validate(q).model_dump(exclude={"answer", "rationale"})
        if include_answers:
            row["answer"] = q.answer
            row["rationale"] = q.rationale or ""
        questions.append(row)

    shares = await section_shares_for_exam(exam.id, db) if is_owner and bank_backed else None

    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": exam.course.name if exam.course else None,
        "time_limit_minutes": exam.time_limit_minutes,
        "pass_grade": exam.pass_grade,
        "shuffle": exam.shuffle,
        "questions_per_attempt": exam.questions_per_attempt,
        # Explicit, so the client never has to infer the gate's outcome from
        # whether a field happens to be missing.
        "answers_included": include_answers,
        "allow_practice": exam.allow_practice,
        "is_owner": is_owner,
        "questions": questions,
        "bank_id": exam.bank_id,
        "bank_backed": bank_backed,
        "section_shares": shares,
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


async def set_settings(
    exam_id: str,
    *,
    time_limit_minutes: int | None,
    set_time_limit: bool,
    shuffle: bool | None,
    questions_per_attempt: int | None,
    clear_questions_per_attempt: bool,
    shares: list[SectionShareIn] | None,
    user: User,
    db: AsyncSession,
) -> Exam:
    """Applies the edit-portal settings strip in one round trip."""
    exam = await get_owned_exam_or_404(exam_id, user, db)
    if set_time_limit:
        exam.time_limit_minutes = time_limit_minutes if time_limit_minutes else None
    if shuffle is not None:
        exam.shuffle = shuffle
    if clear_questions_per_attempt:
        exam.questions_per_attempt = None
    elif questions_per_attempt is not None:
        exam.questions_per_attempt = questions_per_attempt
    if exam.bank_id and shares is not None:
        bank = await banks_service.get_owned_or_404(exam.bank_id, user, db)
        await _validate_shares(shares, {s.id for s in bank.sections}, db, exam.questions_per_attempt)
        await db.execute(delete(ExamSectionShare).where(ExamSectionShare.exam_id == exam.id))
        for share in shares:
            db.add(ExamSectionShare(exam_id=exam.id, section_id=share.section_id, percent=share.percent))
    elif exam.bank_id:
        current = await section_shares_for_exam(exam.id, db)
        if current:
            await _validate_shares(
                [SectionShareIn(section_id=row["section_id"], percent=row["percent"]) for row in current],
                {row["section_id"] for row in current},
                db,
                exam.questions_per_attempt,
            )
    await db.commit()
    return exam


async def delete_exam(exam_id: str, user: User, db: AsyncSession) -> None:
    exam = await get_owned_exam_or_404(exam_id, user, db)
    await _delete(exam, db)


async def _delete(exam: Exam, db: AsyncSession) -> None:
    """Shared by the owner's delete and the admin's, so the image cleanup cannot
    drift between them."""
    # Read the paths before the cascade removes the rows, but only unlink after
    # the commit succeeds — otherwise a failed commit leaves an exam whose
    # images are already gone.
    images = await _image_urls_for_exam(exam.id, db)
    await db.delete(exam)
    await db.commit()
    await run_in_threadpool(remove_upload_files, images)


async def _image_urls_for_exam(exam_id: str, db: AsyncSession) -> list[str]:
    stmt = select(Question.image).where(Question.exam_id == exam_id)
    # Single column, so .scalars() is correct here.
    return [url for url in (await db.execute(stmt)).scalars().all() if url]


# ── Administration ────────────────────────────────────────────────
#
# Cross-owner reads and writes, named `_unscoped` like their counterparts in
# `attempts.service`. Their only callers sit behind the admin gate in
# `platform_admin.router`; nothing here applies `visible()` or an ownership
# filter, which is exactly why the suffix is in the name.


def _admin_filters(query: str | None, owner_id: str | None, shared: bool | None) -> list:
    filters = []
    if owner_id:
        filters.append(Exam.owner_id == owner_id)
    if shared is not None:
        filters.append(Exam.is_shared.is_(shared))
    if query and (needle := query.strip().lower()):
        filters.append(func.lower(Exam.title).like(f"%{needle}%"))
    return filters


async def list_all_unscoped(
    db: AsyncSession,
    query: str | None = None,
    owner_id: str | None = None,
    shared: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Exam]:
    stmt = (
        select(Exam)
        .options(joinedload(Exam.course))
        .where(*_admin_filters(query, owner_id, shared))
        .order_by(Exam.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().unique().all())


async def count_all_unscoped(
    db: AsyncSession, query: str | None = None, owner_id: str | None = None, shared: bool | None = None
) -> int:
    stmt = select(func.count(Exam.id)).where(*_admin_filters(query, owner_id, shared))
    return await db.scalar(stmt) or 0


async def count_all(db: AsyncSession) -> int:
    return await db.scalar(select(func.count(Exam.id))) or 0


async def question_counts_by_exam_ids(exam_ids, db: AsyncSession) -> dict[str, int]:
    """Just the counts, for a listing that shows size but not composition.

    `_type_count_rows` pulls every question's `options` JSONB to classify them,
    which is a lot of payload when the page only prints a number.
    """
    ids = list(exam_ids)
    if not ids:
        return {}
    stmt = select(Question.exam_id, func.count(Question.id)).where(Question.exam_id.in_(ids)).group_by(Question.exam_id)
    return dict((await db.execute(stmt)).all())


async def get_or_404_unscoped(exam_id: str, db: AsyncSession) -> Exam:
    stmt = select(Exam).options(joinedload(Exam.course)).where(Exam.id == exam_id)
    exam = (await db.execute(stmt)).scalars().unique().one_or_none()
    if not exam:
        raise ExamNotFound()
    return exam


async def set_shared_unscoped(exam: Exam, is_shared: bool, db: AsyncSession) -> Exam:
    """The one place `is_shared` is writable after creation, and only for an admin.

    Creation freezes it from the author's role precisely so promoting a student
    never publishes their drafts; unpublishing something already shared is the
    moderation action that has no other route.
    """
    exam.is_shared = is_shared
    await db.commit()
    return exam


async def transfer_owner_unscoped(exam: Exam, owner_id: str, db: AsyncSession) -> Exam:
    exam.owner_id = owner_id
    await db.commit()
    return exam


async def delete_unscoped(exam: Exam, db: AsyncSession) -> None:
    await _delete(exam, db)


async def image_urls_for_owner_unscoped(owner_id: str, db: AsyncSession) -> list[str]:
    """Every question image belonging to one user's exams.

    Deleting an account cascades the exam and question rows away, so the files
    have to be collected before that happens or they are orphaned on the volume
    with nothing left pointing at them.
    """
    stmt = select(Question.image).join(Exam, Question.exam_id == Exam.id).where(Exam.owner_id == owner_id)
    return [url for url in (await db.execute(stmt)).scalars().all() if url]


# ── Questions ─────────────────────────────────────────────────────


def _new_question(exam_id: str, payload: QuestionIn) -> Question:
    return Question(
        exam_id=exam_id,
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
    question = _new_question(exam_id, payload)
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


# ── Bank-backed exams ─────────────────────────────────────────────


def allocate_section_draws(total: int | None, sizes: list[int], percents: list[int]) -> list[int]:
    """How many questions to take from each section.

    When `total` is set, percents are weights of that exam length (largest
    remainder). Unused seats then spill into sections that still have questions
    so the attempt hits `total` whenever the bank can supply it.

    `total is None` is the legacy mix: percent of each section's own size.
    """
    n = len(sizes)
    if n == 0:
        return []
    if total is None:
        return [_share_draw_size(sizes[i], percents[i]) for i in range(n)]

    pool = sum(max(0, size) for size in sizes)
    target = min(max(0, total), pool)
    if target == 0:
        return [0] * n

    weight_sum = sum(max(0, p) for p in percents)
    if weight_sum <= 0:
        return [0] * n

    quotas = [target * max(0, percents[i]) / weight_sum for i in range(n)]
    draws = [min(sizes[i], int(quotas[i])) for i in range(n)]
    leftover = target - sum(draws)
    remainder_order = sorted(range(n), key=lambda i: (quotas[i] - int(quotas[i]), -i), reverse=True)
    for i in remainder_order:
        if leftover <= 0:
            break
        if draws[i] < sizes[i]:
            draws[i] += 1
            leftover -= 1
    room_order = sorted(range(n), key=lambda i: sizes[i] - draws[i], reverse=True)
    while leftover > 0:
        progressed = False
        for i in room_order:
            if leftover <= 0:
                break
            if draws[i] < sizes[i]:
                draws[i] += 1
                leftover -= 1
                progressed = True
        if not progressed:
            break
    return draws


def _share_draw_size(size: int, percent: int) -> int:
    return min(size, max(0, round(size * percent / 100)))


async def _validate_shares(
    shares: list[SectionShareIn], section_ids: set[str], db: AsyncSession, total: int | None = None
) -> None:
    seen: set[str] = set()
    for share in shares:
        if share.section_id in seen:
            raise DuplicateSectionShare()
        seen.add(share.section_id)
        if share.section_id not in section_ids:
            raise SectionNotFound()
    counts = dict(
        (
            await db.execute(
                select(Question.section_id, func.count(Question.id))
                .where(Question.section_id.in_(section_ids))
                .group_by(Question.section_id)
            )
        ).all()
    )
    sizes = [counts.get(share.section_id, 0) for share in shares]
    percents = [share.percent for share in shares]
    if total is not None and total > sum(sizes):
        raise AttemptLargerThanBank()
    expected = sum(allocate_section_draws(total, sizes, percents))
    if expected < 1:
        raise EmptyBankDraw()


async def draw_question_ids(exam_id: str, shuffle_paper: bool, db: AsyncSession) -> list[int]:
    """Sample the live bank for one attempt. Empty list means the mix currently draws nothing."""
    share_rows = (
        await db.execute(
            select(ExamSectionShare, BankSection.position)
            .join(BankSection, ExamSectionShare.section_id == BankSection.id)
            .where(ExamSectionShare.exam_id == exam_id)
            .order_by(BankSection.position, BankSection.id)
        )
    ).all()
    if not share_rows:
        return []
    section_ids = [share.section_id for share, _pos in share_rows]
    q_rows = (
        await db.execute(select(Question.id, Question.section_id).where(Question.section_id.in_(section_ids)))
    ).all()
    by_section: dict[str, list[int]] = {sid: [] for sid in section_ids}
    for qid, sid in q_rows:
        by_section.setdefault(sid, []).append(qid)
    total = await db.scalar(select(Exam.questions_per_attempt).where(Exam.id == exam_id))
    sizes = [len(by_section.get(share.section_id, [])) for share, _pos in share_rows]
    percents = [share.percent for share, _pos in share_rows]
    ns = allocate_section_draws(total, sizes, percents)
    drawn: list[int] = []
    for (share, _pos), n in zip(share_rows, ns, strict=True):
        pool = by_section.get(share.section_id, [])
        if n:
            drawn.extend(random.sample(pool, n))
    if shuffle_paper:
        random.shuffle(drawn)
    return drawn


async def draw_attempt_order(exam_id: str, shuffle_paper: bool, db: AsyncSession) -> list[int]:
    drawn = await draw_question_ids(exam_id, shuffle_paper, db)
    if not drawn:
        raise EmptyBankDraw()
    return drawn


async def bank_pool_questions(exam_id: str, db: AsyncSession) -> list[Question]:
    stmt = (
        select(Question)
        .join(ExamSectionShare, Question.section_id == ExamSectionShare.section_id)
        .join(BankSection, Question.section_id == BankSection.id)
        .where(ExamSectionShare.exam_id == exam_id)
        .order_by(BankSection.position, Question.id)
    )
    return list((await db.execute(stmt)).scalars().unique().all())


async def section_shares_for_exam(exam_id: str, db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(
                ExamSectionShare.section_id,
                ExamSectionShare.percent,
                BankSection.name,
                func.count(Question.id),
            )
            .join(BankSection, ExamSectionShare.section_id == BankSection.id)
            .outerjoin(Question, Question.section_id == BankSection.id)
            .where(ExamSectionShare.exam_id == exam_id)
            .group_by(
                ExamSectionShare.section_id,
                ExamSectionShare.percent,
                BankSection.name,
                BankSection.position,
            )
            .order_by(BankSection.position)
        )
    ).all()
    return [
        {"section_id": section_id, "percent": percent, "name": name, "question_count": count}
        for section_id, percent, name, count in rows
    ]


async def bank_has_exams(bank_id: str, db: AsyncSession) -> bool:
    return (await db.scalar(select(Exam.id).where(Exam.bank_id == bank_id).limit(1))) is not None


async def image_urls_for_bank(bank_id: str, db: AsyncSession) -> list[str]:
    stmt = (
        select(Question.image)
        .join(BankSection, Question.section_id == BankSection.id)
        .where(BankSection.bank_id == bank_id)
    )
    return [url for url in (await db.execute(stmt)).scalars().all() if url]


async def image_urls_for_section(section_id: str, db: AsyncSession) -> list[str]:
    stmt = select(Question.image).where(Question.section_id == section_id)
    return [url for url in (await db.execute(stmt)).scalars().all() if url]


async def remove_images(urls: list[str]) -> None:
    await run_in_threadpool(remove_upload_files, urls)


def _new_section_question(section_id: str, payload: QuestionIn) -> Question:
    return Question(
        section_id=section_id,
        topic=payload.topic,
        type=payload.type,
        question=payload.question,
        sections=payload.sections,
        options=payload.options,
        answer=payload.answer,
        rationale=payload.rationale,
    )


async def add_questions_to_section(
    bank_id: str, section_id: str, questions: list[QuestionIn], user, db: AsyncSession
) -> int:
    await banks_service.get_owned_section_or_404(bank_id, section_id, user, db)
    for q in questions:
        db.add(_new_section_question(section_id, q))
    await db.commit()
    return len(questions)


async def get_owned_question_in_section_or_404(
    bank_id: str, section_id: str, question_id: int, user, db: AsyncSession
) -> Question:
    stmt = (
        select(Question)
        .join(BankSection, Question.section_id == BankSection.id)
        .join(QuestionBank, BankSection.bank_id == QuestionBank.id)
        .where(
            Question.id == question_id,
            Question.section_id == section_id,
            BankSection.bank_id == bank_id,
            QuestionBank.owner_id == user.id,
        )
    )
    question = (await db.execute(stmt)).scalar_one_or_none()
    if not question:
        raise QuestionNotFound()
    return question


async def update_section_question(
    bank_id: str, section_id: str, question_id: int, payload: QuestionUpdate, user, db: AsyncSession
) -> Question:
    question = await get_owned_question_in_section_or_404(bank_id, section_id, question_id, user, db)
    nullable = {"sections", "options", "answer"}
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if field in nullable or value is not None:
            setattr(question, field, value)
    await db.commit()
    return question


async def delete_section_question(bank_id: str, section_id: str, question_id: int, user, db: AsyncSession) -> None:
    question = await get_owned_question_in_section_or_404(bank_id, section_id, question_id, user, db)
    image = question.image
    await db.delete(question)
    await db.commit()
    await run_in_threadpool(remove_upload_file, image)
