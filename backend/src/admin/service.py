from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.exceptions import StudentNotFound
from src.attempts import service as attempts_service
from src.attempts.constants import AttemptMode
from src.auth import service as auth_service
from src.exams import service as exams_service
from src.grading.constants import DEFAULT_PASS_GRADE
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
    exam_settings = await exams_service.settings_by_exam_ids(exam_ids, db) if exam_ids else {}
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
        # The exam may have been deleted while the attempt was open, in which case
        # nothing is left to read the threshold from.
        time_limit, pass_grade = exam_settings.get(r.exam_id, (None, DEFAULT_PASS_GRADE))
        out.append(
            {
                "id": r.id,
                "exam_id": r.exam_id,
                "exam_title": r.exam_title,
                "pass_grade": pass_grade,
                "student_name": r.user.display_name if r.user else None,
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
                "remaining_seconds": _remaining_seconds(r, time_limit, now),
            }
        )
    return out


# ── Instructor analytics ──────────────────────────────────────────
#
# Read views composed from other domains' services. Note the layering rule this
# module keeps: it imports no models, so every cross-user query lives in the
# domain that owns the table and carries its own instructor_id filter.

_NO_ATTEMPTS = {
    "attempts": 0,
    "exam_attempts": 0,
    "practice_attempts": 0,
    "average_score": 0.0,
    "best_score": 0.0,
    "pass_rate": 0,
    "total_seconds": 0,
    "last_attempt_at": None,
}

# Two weeks of activity: long enough to show a trend, short enough that every
# label fits on a phone.
ACTIVITY_DAYS = 14
RECENT_DAYS = 30


def _student_item(student, rollup: dict, in_progress: int) -> dict:
    """The one place StudentItemOut's shape is assembled."""
    return {
        "id": student.id,
        "display_name": student.display_name,
        "email": student.email,
        "avatar": student.avatar,
        "in_progress_count": in_progress,
        "joined_at": student.created_at,
        **rollup,
    }


async def build_students(user, db: AsyncSession) -> list[dict]:
    """The caller's students, each with their aggregates.

    Driven by the roster rather than by the history rows: a student who has
    enrolled but not yet sat anything must appear with zeros, otherwise the page
    silently looks empty to an instructor whose class has just signed up.
    """
    students = await auth_service.list_students(user.id, db)
    rollups = await attempts_service.student_rollups(user.id, db)
    open_counts = await attempts_service.in_progress_counts(user.id, db)

    return [_student_item(s, rollups.get(s.id, _NO_ATTEMPTS), open_counts.get(s.id, 0)) for s in students]


async def build_student_detail(user, student_id: str, db: AsyncSession) -> dict:
    """One student's drill-down.

    A student who is not this instructor's raises the same 404 as one who does not
    exist — a 403 here would confirm that an id belongs to a real account.
    """
    student = await auth_service.get_by_id(student_id, db)
    if not student or student.instructor_id != user.id:
        raise StudentNotFound()

    rollups = await attempts_service.student_rollups(user.id, db)
    open_counts = await attempts_service.in_progress_counts(user.id, db)
    attempts = await attempts_service.list_history_for_student(student_id, user.id, db)
    topics = await attempts_service.topic_stats_for_student(student_id, user.id, db)

    return {
        "student": _student_item(student, rollups.get(student_id, _NO_ATTEMPTS), open_counts.get(student_id, 0)),
        "recent_attempts": attempts,
        "topic_stats": topics,
    }


async def build_instructor_overview(user, db: AsyncSession) -> dict:
    """Everything the instructor landing page needs, in one request.

    Sequential rather than gathered: these all share one AsyncSession, and
    concurrent queries on a single session raise InterfaceError.
    """
    students = await auth_service.list_students(user.id, db)
    totals = await attempts_service.class_totals(user.id, RECENT_DAYS, db)
    open_counts = await attempts_service.in_progress_counts(user.id, db)
    exam_count = await exams_service.count_owned(user, db)
    per_day = await attempts_service.attempts_per_day(user.id, ACTIVITY_DAYS, db)
    buckets = await attempts_service.score_buckets(user.id, db)
    rollups = await attempts_service.exam_rollups(user.id, db)
    topics = await attempts_service.topic_stats_for_instructor(user.id, db)

    attempts = totals["attempts"]
    return {
        "student_count": len(students),
        "exam_count": exam_count,
        "attempts": attempts,
        "recent_attempts": totals["recent_attempts"],
        "live_now": sum(open_counts.values()),
        "average_score": totals["average_score"],
        "pass_rate": totals["pass_rate"],
        "total_seconds": totals["total_seconds"],
        "invite_code": user.invite_code,
        "attempts_per_day": per_day,
        "score_buckets": buckets,
        "passed_count": totals["passed_count"],
        "failed_count": attempts - totals["passed_count"],
        "exam_rollups": rollups,
        "topic_stats": topics,
    }
