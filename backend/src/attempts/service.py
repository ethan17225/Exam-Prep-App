from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.attempts.exceptions import NoValidQuestions, RecordNotFound
from src.attempts.models import History, InProgressExam
from src.attempts.schemas import ExamSubmission, SaveProgressPayload
from src.auth.models import User
from src.exams.models import Exam
from src.grading.constants import PASS_THRESHOLD
from src.grading.service import grade_question, is_fib_question


def in_progress_to_dict(record) -> dict:
    return {
        "id": record.id,
        "exam_id": record.exam_id,
        "exam_title": record.exam_title,
        "mode": record.mode,
        "answers": record.answers,
        "flagged": record.flagged,
        "question_order": record.question_order,
        "remaining_seconds": record.remaining_seconds,
        "current_page": record.current_page,
        "total_questions": record.total_questions,
        "answered_count": record.answered_count,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "saved_at": record.saved_at.isoformat(),
    }


def history_summary(record: History) -> dict:
    """Everything the history list renders, minus the heavy `results` blob."""
    return {
        "id": record.id,
        "exam_id": record.exam_id,
        "exam_title": record.exam_title,
        "score": record.score,
        "correct": record.correct,
        "total": record.total,
        "passed": record.passed,
        "time_spent_seconds": record.time_spent_seconds,
        "mode": record.mode or "exam",
        "taken_at": record.taken_at.isoformat(),
    }


def history_to_dict(record: History) -> dict:
    return {**history_summary(record), "results": record.results}


async def rename_exam(exam_id: str, new_title: str, db: AsyncSession) -> None:
    """Fan a renamed exam out to the denormalized copies.

    Called from `exams.router`, never from `exams.service` — this is the one
    dependency edge that points up the layering, and routers are import sinks.
    Add any future denormalized copy of `exam_title` here.
    """
    await db.execute(update(History).where(History.exam_id == exam_id).values(exam_title=new_title))
    await db.execute(update(InProgressExam).where(InProgressExam.exam_id == exam_id).values(exam_title=new_title))


# ── In-progress ───────────────────────────────────────────────────


async def save_progress(payload: SaveProgressPayload, exam: Exam, user: User, db: AsyncSession) -> dict:
    now = datetime.now()
    stmt = pg_insert(InProgressExam.__table__).values(
        id=str(uuid4())[:8],
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
    return in_progress_to_dict(record)


async def list_in_progress(user: User, db: AsyncSession) -> list[dict]:
    stmt = select(InProgressExam).where(InProgressExam.user_id == user.id).order_by(InProgressExam.saved_at.desc())
    return [in_progress_to_dict(r) for r in (await db.execute(stmt)).scalars().all()]


async def list_in_progress_unscoped(limit: int, db: AsyncSession):
    """Every user's live attempts. The ONLY query in the app that crosses users.

    Instructor-only: its single caller is `admin.router`, which is gated by
    InstructorDep and covered by a test asserting that gate.
    """
    stmt = (
        select(InProgressExam)
        .options(joinedload(InProgressExam.user))
        .order_by(InProgressExam.saved_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().unique().all())


async def get_in_progress_or_404(record_id: str, user: User, db: AsyncSession) -> InProgressExam:
    stmt = select(InProgressExam).where(InProgressExam.id == record_id, InProgressExam.user_id == user.id)
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        raise RecordNotFound()
    return record


async def delete_in_progress(record_id: str, user: User, db: AsyncSession) -> None:
    record = await get_in_progress_or_404(record_id, user, db)
    await db.delete(record)
    await db.commit()


async def delete_in_progress_by_exam(exam_id: str, mode: str, user: User, db: AsyncSession) -> None:
    stmt = select(InProgressExam).where(
        InProgressExam.exam_id == exam_id,
        InProgressExam.mode == mode,
        InProgressExam.user_id == user.id,
    )
    record = (await db.execute(stmt)).scalar_one_or_none()
    if record:
        await db.delete(record)
        await db.commit()


# ── Submit ────────────────────────────────────────────────────────


async def submit(exam: Exam, submission: ExamSubmission, user: User, db: AsyncSession) -> dict:
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
            is_correct = grade_question(q, user_answer)

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
        id=str(uuid4())[:8],
        user_id=user.id,
        exam_id=exam.id,
        exam_title=exam.title,
        score=round(score * 100, 1),
        correct=correct_count,
        total=total,
        passed=score >= PASS_THRESHOLD,
        time_spent_seconds=submission.time_spent_seconds,
        results=results,
        mode=submission.mode,
        taken_at=datetime.now(),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return history_to_dict(record)


# ── History ───────────────────────────────────────────────────────


async def list_history(user: User, limit: int, offset: int, db: AsyncSession) -> list[dict]:
    stmt = (
        select(History).where(History.user_id == user.id).order_by(History.taken_at.desc()).limit(limit).offset(offset)
    )
    return [history_summary(r) for r in (await db.execute(stmt)).scalars().all()]


async def topic_stats(user: User, db: AsyncSession) -> list[dict]:
    """Per-topic correct/total across all of this user's attempts.

    Aggregated in Postgres rather than by shipping every `results` blob to the
    browser — this is the only thing the overview page needed them for.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(elem->>'topic', '') AS topic,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE (elem->>'is_correct')::boolean) AS correct
                FROM history, LATERAL jsonb_array_elements(history.results) AS elem
                WHERE history.user_id = :user_id
                GROUP BY 1
                """
            ),
            {"user_id": user.id},
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
    stats.sort(key=lambda s: s["score"], reverse=True)
    return stats


async def get_history_or_404(record_id: str, user: User, db: AsyncSession) -> History:
    stmt = select(History).where(History.id == record_id, History.user_id == user.id)
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        raise RecordNotFound()
    return record


async def delete_history(record_id: str, user: User, db: AsyncSession) -> None:
    record = await get_history_or_404(record_id, user, db)
    await db.delete(record)
    await db.commit()
