from pydantic import BaseModel

from src.schemas import ISODateTime


class DashboardItemOut(BaseModel):
    """One student's live attempt. Built by `service.build_dashboard` — the
    counts come from re-grading, so this is not a projection of a row."""

    id: str
    exam_id: str
    exam_title: str
    pass_grade: int
    student_name: str | None
    student_email: str | None
    mode: str
    total_questions: int
    answered_count: int
    remaining_count: int
    correct_count: int
    wrong_count: int
    score_percent: float
    started_at: ISODateTime | None
    saved_at: ISODateTime
    seconds_since_last_answer: int
    seconds_since_start: int | None
    remaining_seconds: int


class StudentItemOut(BaseModel):
    """One student plus their aggregates. Built by `service.build_students`, which
    merges the roster with the SQL rollups so a student with no attempts yet still
    appears — with zeros rather than being absent."""

    id: str
    display_name: str | None
    email: str
    avatar: str | None
    attempts: int
    exam_attempts: int
    practice_attempts: int
    average_score: float
    best_score: float
    pass_rate: int
    total_seconds: int
    in_progress_count: int
    last_attempt_at: ISODateTime | None
    joined_at: ISODateTime


class TopicStatOut(BaseModel):
    topic: str
    total: int
    correct: int
    score: int


class StudentAttemptOut(BaseModel):
    """An attempt as it appears in the instructor's drill-down. Deliberately
    without the `results` blob — listing those is what made the student-facing
    history endpoint a multi-megabyte response."""

    id: str
    exam_id: str
    exam_title: str
    score: float
    correct: int
    total: int
    passed: bool
    pass_grade: int
    mode: str
    over_time: bool
    time_spent_seconds: int
    taken_at: ISODateTime


class StudentDetailOut(BaseModel):
    student: StudentItemOut
    recent_attempts: list[StudentAttemptOut]
    topic_stats: list[TopicStatOut]


class ExamRollupOut(BaseModel):
    exam_id: str
    exam_title: str
    pass_grade: int
    attempts: int
    students: int
    average_score: float
    pass_rate: int
    last_attempt_at: ISODateTime | None


class DailyPointOut(BaseModel):
    day: str
    attempts: int
    average_score: float


class InstructorOverviewOut(BaseModel):
    """Everything the instructor landing page renders, in one request. Built by
    `service.build_instructor_overview`."""

    student_count: int
    exam_count: int
    attempts: int
    recent_attempts: int
    live_now: int
    average_score: float
    pass_rate: int
    total_seconds: int
    # The instructor's own enrolment code, repeated here so the "no students yet"
    # empty state can show it without a second request.
    invite_code: str | None
    attempts_per_day: list[DailyPointOut]
    score_buckets: list[int]
    passed_count: int
    failed_count: int
    exam_rollups: list[ExamRollupOut]
    topic_stats: list[TopicStatOut]
