from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.attempts import service as attempts_service
from src.attempts.constants import AttemptMode
from src.exams import service as exams_service
from src.grading.service import GradableRow, grade_question


def _remaining_seconds(record, time_limit_minutes: int | None, now: datetime) -> int:
    """Time left, derived from the server's `started_at`.

    The stored `remaining_seconds` is whatever the student's browser last
    reported, so it must not be what a proctor reads. Untimed exams fall back to
    the client value, which is decorative there.
    """
    if not time_limit_minutes:
        return record.remaining_seconds
    elapsed = (now - record.started_at).total_seconds()
    return max(0, int(time_limit_minutes * 60 - elapsed))


async def build_dashboard(limit: int, db: AsyncSession) -> list[dict]:
    """Live view of every student's in-progress attempt.

    Composes other domains' services rather than importing their models — admin
    is a cross-domain read view, not an owner of anything.
    """
    rows = await attempts_service.list_in_progress_unscoped(limit, db)

    # One query for every exam on the page instead of one per row, and only the
    # columns grading reads.
    exam_ids = {r.exam_id for r in rows}
    # Time limits, so the countdown shown to the proctor is derived from the
    # server's started_at rather than echoing back the student's own number.
    limits = await exams_service.time_limits_by_exam_ids(exam_ids, db) if exam_ids else {}
    questions_by_exam: dict[str, dict[int, GradableRow]] = {eid: {} for eid in exam_ids}
    if exam_ids:
        for exam_id, number, qtype, answer, options in await exams_service.questions_by_exam_ids(exam_ids, db):
            questions_by_exam[exam_id][number] = GradableRow(qtype, answer, options)

    now = datetime.now()
    out = []
    for r in rows:
        correct_count = 0
        wrong_count = 0
        q_map = questions_by_exam.get(r.exam_id, {})
        for qnum_str, user_answer in (r.answers or {}).items():
            # Answer keys arrive from the client; a non-numeric key must not
            # wedge this endpoint for every instructor.
            try:
                q = q_map.get(int(qnum_str))
            except (TypeError, ValueError):
                continue
            if not q:
                continue
            # Same strictness the final grade will use, so the proctor's view and
            # the History score cannot disagree.
            if grade_question(q, user_answer, fuzzy_fib=r.mode != AttemptMode.EXAM):
                correct_count += 1
            else:
                wrong_count += 1

        answered = correct_count + wrong_count
        out.append(
            {
                "id": r.id,
                "exam_id": r.exam_id,
                "exam_title": r.exam_title,
                "student_email": r.user.email if r.user else None,
                "mode": r.mode,
                "total_questions": r.total_questions,
                "answered_count": r.answered_count,
                # Clamped: a client that autosaves answers with an empty
                # question_order would otherwise show a negative remainder.
                "remaining_count": max(0, r.total_questions - r.answered_count),
                "correct_count": correct_count,
                "wrong_count": wrong_count,
                "score_percent": round((correct_count / answered) * 100, 1) if answered else 0,
                "started_at": r.started_at,
                "saved_at": r.saved_at,
                "seconds_since_last_answer": (int((now - r.saved_at).total_seconds()) if r.saved_at else 0),
                "seconds_since_start": (int((now - r.started_at).total_seconds()) if r.started_at else None),
                "remaining_seconds": _remaining_seconds(r, limits.get(r.exam_id), now),
            }
        )
    return out
