from datetime import datetime, timedelta

from sqlalchemy import Row, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.attempts.constants import SUBMIT_GRACE_SECONDS, AttemptMode
from src.attempts.exceptions import (
    AttemptExpired,
    AttemptNotDiscardable,
    AttemptNotOpen,
    ExamIdMismatch,
    NoValidQuestions,
    PracticeDisabled,
    RecordNotFound,
)
from src.attempts.models import History, InProgressExam
from src.attempts.schemas import ExamSubmission, SaveProgressPayload
from src.auth.models import User
from src.constants import MAX_INT
from src.exams.models import Exam
from src.grading.constants import PASS_THRESHOLD
from src.grading.service import grade_question, is_fib_question
from src.identifiers import new_id

# Both attempt tables are strictly caller-scoped: every read and every delete
# filters on user_id. `list_in_progress_unscoped` is the one exception and says
# so in its name.


async def _owned_or_404(model, record_id: str, user: User, db: AsyncSession):
    stmt = select(model).where(model.id == record_id, model.user_id == user.id)
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        raise RecordNotFound()
    return record


async def _delete_owned(model, record_id: str, user: User, db: AsyncSession) -> None:
    record = await _owned_or_404(model, record_id, user, db)
    await db.delete(record)
    await db.commit()


async def rename_exam(exam_id: str, new_title: str, db: AsyncSession) -> None:
    """Fan a renamed exam out to the denormalized copies, and commit.

    Called from `exams.router`, never from `exams.service` — this is the one
    dependency edge that points up the layering, and routers are import sinks.
    It commits deliberately: `exams.service.rename` has already staged the title
    change on the same session, and both must land in one transaction.

    Add any future denormalized copy of `exam_title` here.
    """
    for model in (History, InProgressExam):
        await db.execute(update(model).where(model.exam_id == exam_id).values(exam_title=new_title))
    await db.commit()


# ── In-progress ───────────────────────────────────────────────────


def _deadline(exam: Exam, started_at: datetime) -> datetime | None:
    """When answers stop being accepted, or None if the exam is untimed."""
    if not exam.time_limit_minutes:
        return None
    return started_at + timedelta(minutes=exam.time_limit_minutes, seconds=SUBMIT_GRACE_SECONDS)


async def _open_attempt(exam_id: str, mode: AttemptMode, user: User, db: AsyncSession):
    """The caller's open attempt, locked for update.

    FOR UPDATE is what makes two simultaneous submits safe: the second blocks,
    and once the first commits its delete the locked read returns nothing, so the
    loser gets AttemptNotOpen instead of writing a second History row.
    """
    stmt = (
        select(InProgressExam)
        .where(
            InProgressExam.user_id == user.id,
            InProgressExam.exam_id == exam_id,
            InProgressExam.mode == mode,
        )
        .with_for_update()
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def save_progress(payload: SaveProgressPayload, exam: Exam, user: User, db: AsyncSession) -> Row:
    """Returns the upserted row. It is a Core `Row`, not an ORM instance —
    `InProgressOut` reads it by attribute either way."""
    if payload.mode is AttemptMode.PRACTICE and not exam.allow_practice:
        raise PracticeDisabled()

    if payload.mode is AttemptMode.EXAM:
        existing = await _open_attempt(exam.id, payload.mode, user, db)
        deadline = _deadline(exam, existing.started_at) if existing else None
        if deadline and datetime.now() > deadline:
            # Refuse further answers once time is up. The attempt row is left in
            # place so the student can still submit what the server already has.
            raise AttemptExpired()

    now = datetime.now()
    stmt = pg_insert(InProgressExam.__table__).values(
        id=new_id(),
        user_id=user.id,
        exam_id=payload.exam_id,
        exam_title=exam.title,
        mode=payload.mode,
        answers=payload.answers,
        flagged=payload.flagged,
        question_order=payload.question_order,
        remaining_seconds=payload.remaining_seconds,
        current_page=payload.current_page,
        total_questions=len(payload.question_order),
        answered_count=len(payload.answers),
        started_at=now,
        saved_at=now,
    )
    # id and started_at are deliberately absent from the update: rewriting id
    # breaks the live resume link, and rewriting started_at resets the
    # dashboard's elapsed timer on every autosave.
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "exam_id", "mode"],
        set_={
            "exam_title": stmt.excluded.exam_title,
            "answers": stmt.excluded.answers,
            "flagged": stmt.excluded.flagged,
            "question_order": stmt.excluded.question_order,
            "remaining_seconds": stmt.excluded.remaining_seconds,
            "current_page": stmt.excluded.current_page,
            "total_questions": stmt.excluded.total_questions,
            "answered_count": stmt.excluded.answered_count,
            "saved_at": stmt.excluded.saved_at,
        },
    ).returning(InProgressExam.__table__)
    # RETURNING rather than a follow-up SELECT: one round trip on the hottest
    # write path, and no chance of reading a stale identity-map row.
    record = (await db.execute(stmt)).one()
    await db.commit()
    return record


async def list_in_progress(user: User, db: AsyncSession) -> list[InProgressExam]:
    stmt = select(InProgressExam).where(InProgressExam.user_id == user.id).order_by(InProgressExam.saved_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_in_progress_unscoped(limit: int, db: AsyncSession) -> list[InProgressExam]:
    """Every user's live attempts. The ONLY query in the app that crosses users.

    Instructor-only: its single caller is `admin.service`, reached through a
    route gated by InstructorDep and covered by a test asserting that gate.
    """
    stmt = (
        select(InProgressExam)
        .options(joinedload(InProgressExam.user))
        .order_by(InProgressExam.saved_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().unique().all())


async def get_in_progress_or_404(record_id: str, user: User, db: AsyncSession) -> InProgressExam:
    return await _owned_or_404(InProgressExam, record_id, user, db)


async def delete_in_progress(record_id: str, user: User, db: AsyncSession) -> None:
    record = await _owned_or_404(InProgressExam, record_id, user, db)
    _refuse_if_graded(record.mode)
    await db.delete(record)
    await db.commit()


async def delete_in_progress_by_exam(exam_id: str, mode: AttemptMode, user: User, db: AsyncSession) -> None:
    _refuse_if_graded(mode)
    stmt = select(InProgressExam).where(
        InProgressExam.exam_id == exam_id,
        InProgressExam.mode == mode,
        InProgressExam.user_id == user.id,
    )
    record = (await db.execute(stmt)).scalar_one_or_none()
    if record:
        await db.delete(record)
        await db.commit()


def _refuse_if_graded(mode: str) -> None:
    """A student discarding a graded attempt would reset its server-side clock,
    so only an instructor can clear one (see admin.service.reset_attempt)."""
    if mode == AttemptMode.EXAM:
        raise AttemptNotDiscardable()


async def reset_attempt_unscoped(record_id: str, db: AsyncSession) -> None:
    """Clear any user's attempt. Instructor-only — the companion to
    `_refuse_if_graded`, without which an abandoned graded attempt would lock a
    student out of that exam permanently."""
    record = (await db.execute(select(InProgressExam).where(InProgressExam.id == record_id))).scalar_one_or_none()
    if not record:
        raise RecordNotFound()
    await db.delete(record)
    await db.commit()


# ── Submit ────────────────────────────────────────────────────────


async def submit(exam: Exam, submission: ExamSubmission, user: User, db: AsyncSession) -> History:
    if submission.exam_id != exam.id:
        raise ExamIdMismatch()

    mode = submission.mode
    graded = mode is AttemptMode.EXAM
    if mode is AttemptMode.PRACTICE and not exam.allow_practice:
        raise PracticeDisabled()

    # An attempt must exist. Deleting it in the same transaction as the History
    # insert is what makes submission at-most-once.
    attempt = await _open_attempt(exam.id, mode, user, db)
    if not attempt:
        raise AttemptNotOpen()

    now = datetime.now()
    deadline = _deadline(exam, attempt.started_at)
    over_time = bool(graded and deadline and now > deadline)

    fib_mark_map: dict[int, bool] = {}
    if graded:
        # The clock belongs to the server. An overrun graded run is scored
        # against the last autosave accepted before the bell rather than against
        # whatever the browser still holds — so no attempt is destroyed by a 4xx,
        # and work done after time is up does not count.
        elapsed = max(0, min(int((now - attempt.started_at).total_seconds()), MAX_INT))
        if over_time:
            answer_map = {int(k): v for k, v in (attempt.answers or {}).items()}
        else:
            answer_map = {a.question_number: a.answer for a in submission.answers}
        # Self-marking and client-chosen question subsets are practice-only.
        selected_questions = list(exam.questions)
    else:
        elapsed = submission.time_spent_seconds
        answer_map = {a.question_number: a.answer for a in submission.answers}
        fib_mark_map = {a.question_number: a.fib_correct for a in submission.answers if a.fib_correct is not None}
        selected_questions = exam.questions
        if submission.question_numbers:
            selected_set = set(submission.question_numbers)
            selected_questions = [q for q in exam.questions if q.number in selected_set]
            if not selected_questions:
                raise NoValidQuestions()

    results = []
    correct_count = 0
    for q in selected_questions:
        user_answer = answer_map.get(q.number)

        if is_fib_question(q) and q.number in fib_mark_map:
            is_correct = fib_mark_map[q.number]
        else:
            # Graded FIB is exact/numeric only. The lenient substring match is a
            # study aid; with self-marking gone it would otherwise *be* the grade.
            is_correct = grade_question(q, user_answer, fuzzy_fib=not graded)

        if is_correct:
            correct_count += 1

        results.append(
            {
                "question_number": q.number,
                "question": q.question,
                "topic": q.topic,
                "type": q.type,
                "sections": q.sections,
                "options": q.options,
                "image": q.image,
                "user_answer": user_answer,
                "correct_answer": q.answer,
                "is_correct": is_correct,
                "rationale": q.rationale or "",
            }
        )

    total = len(selected_questions)
    score = correct_count / total if total else 0
    record = History(
        id=new_id(),
        user_id=user.id,
        exam_id=exam.id,
        exam_title=exam.title,
        score=round(score * 100, 1),
        correct=correct_count,
        total=total,
        passed=score >= PASS_THRESHOLD,
        time_spent_seconds=elapsed,
        over_time=over_time,
        results=results,
        mode=mode,
        taken_at=now,
    )
    db.add(record)
    # Same transaction as the insert: consuming the attempt is what stops a
    # second submit producing a second History row.
    await db.delete(attempt)
    await db.commit()
    return record


# ── History ───────────────────────────────────────────────────────


async def list_history(user: User, limit: int, offset: int, db: AsyncSession) -> list[History]:
    stmt = (
        select(History).where(History.user_id == user.id).order_by(History.taken_at.desc()).limit(limit).offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())


async def topic_stats(user: User, db: AsyncSession, attempt_limit: int = 500) -> list[dict]:
    """Per-topic correct/total across this user's most recent attempts.

    Aggregated in Postgres rather than by shipping every `results` blob to the
    browser — this is the only thing the overview page needed them for. Bounded
    to the newest `attempt_limit` attempts: unbounded, a heavy user expanded
    hundreds of thousands of JSONB elements per page load, with no rate limit.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(elem->>'topic', '') AS topic,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE (elem->>'is_correct')::boolean) AS correct
                FROM (
                    SELECT results FROM history
                    WHERE user_id = :user_id
                    ORDER BY taken_at DESC
                    LIMIT :attempt_limit
                ) recent, LATERAL jsonb_array_elements(recent.results) AS elem
                GROUP BY 1
                """
            ),
            {"user_id": user.id, "attempt_limit": attempt_limit},
        )
    ).all()

    stats = [
        {
            "topic": topic,
            "total": total,
            "correct": correct,
            "score": round((correct / total) * 100) if total else 0,
        }
        for topic, total, correct in rows
    ]
    # Sorted here rather than in SQL: `score` is derived, so ordering by it in
    # the query means repeating the ratio expression. The list is one row per
    # topic — tens of items, not thousands.
    stats.sort(key=lambda s: s["score"], reverse=True)
    return stats


async def get_history_or_404(record_id: str, user: User, db: AsyncSession) -> History:
    return await _owned_or_404(History, record_id, user, db)


async def delete_history(record_id: str, user: User, db: AsyncSession) -> None:
    await _delete_owned(History, record_id, user, db)
