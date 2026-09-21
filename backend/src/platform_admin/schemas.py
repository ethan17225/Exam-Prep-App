from pydantic import BaseModel, EmailStr, Field

from src.auth.constants import UserRole
from src.auth.models import DISPLAY_NAME_MAX
from src.identifiers import ID_LENGTH
from src.schemas import DailyPointOut, ISODateTime, StudentAttemptOut, TopicStatOut

# Free-text search bound. Long enough for an email, short enough that the LIKE
# pattern cannot be used to ship a megabyte per request.
SEARCH_MAX = 120

# Shared by every password field here and in `auth.schemas`: bcrypt hard-limits
# its input at 72 bytes and silently ignores the rest, so a longer value would be
# a password that is not fully checked.
PasswordField = Field(min_length=8, max_length=72)
IdField = Field(max_length=ID_LENGTH)


# ── Users ─────────────────────────────────────────────────────────


class UserItemOut(BaseModel):
    """One account as the Users table lists it.

    Assembled by `service._user_item` — the counts are batched aggregates rather
    than columns, so this is not a projection of a row.
    """

    id: str
    email: EmailStr
    role: UserRole
    # None until onboarding sets it, which is also how the page flags an account
    # that has registered but never finished signing up.
    display_name: str | None
    avatar: str | None
    # Set for staff only. It is a credential — anyone holding it can enrol
    # students under that instructor — so it is returned to admins alone.
    invite_code: str | None
    instructor_id: str | None
    instructor_name: str | None
    # Size of this account's own roster. Always 0 for a student.
    student_count: int
    attempts: int
    in_progress_count: int
    created_at: ISODateTime


class UserRollupOut(BaseModel):
    attempts: int
    exam_attempts: int
    practice_attempts: int
    average_score: float
    best_score: float
    pass_rate: int
    total_seconds: int
    last_attempt_at: ISODateTime | None


class UserDetailOut(BaseModel):
    user: UserItemOut
    rollup: UserRollupOut
    owned_exams: int
    owned_courses: int
    # Populated for staff only: the accounts enrolled with this one.
    students: list[UserItemOut]
    recent_attempts: list[StudentAttemptOut]


class UserPageOut(BaseModel):
    items: list[UserItemOut]
    # The count for the current filter, not the table — the page needs it to know
    # whether another page exists.
    total: int
    limit: int
    offset: int


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = PasswordField
    # Any role, including another admin: the admin gate replaces the invite code
    # that `POST /api/auth/register` requires. This is the only path that mints an
    # admin, which is why it is behind that gate and audited.
    role: UserRole = UserRole.STUDENT
    # Optional, and setting it lets the new account skip onboarding entirely.
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX)
    # Required for a student and ignored for staff; validated to be a real
    # instructor or admin rather than trusted.
    instructor_id: str | None = Field(default=None, max_length=ID_LENGTH)


class UserUpdateIn(BaseModel):
    """Partial update. Absent fields are untouched; `instructor_id: null`
    unenrols. The service reads `model_fields_set` to tell the two apart."""

    role: UserRole | None = None
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX)
    instructor_id: str | None = Field(default=None, max_length=ID_LENGTH)


class PasswordResetIn(BaseModel):
    # No current password, unlike `PasswordChangeIn` — that is the difference
    # between an admin reset and the self-service change, and the reason the two
    # are separate endpoints rather than one with a flag.
    new_password: str = PasswordField


class ReassignIn(BaseModel):
    to_instructor_id: str = IdField


class ReassignedOut(BaseModel):
    moved: int


class InviteCodeOut(BaseModel):
    invite_code: str


class RevokedOut(BaseModel):
    revoked: bool


class UpdatedOut(BaseModel):
    """Acknowledgement for the two moderation PATCHes.

    Not `DeletedOut`: a moderation response of `{"deleted": false}` reads as a
    failed delete. The updated row is not returned because the caller has to
    refetch regardless — unpublishing while the shared filter is active changes
    which rows belong on the page, not just the row that was edited.
    """

    updated: bool


# ── Instructors ───────────────────────────────────────────────────


class InstructorItemOut(BaseModel):
    """A staff member and how their class is doing. Built by
    `attempts.service.instructor_rollups`, which is driven from the roster so an
    instructor with no students still appears with zeros."""

    instructor_id: str
    display_name: str | None
    email: EmailStr
    role: UserRole
    invite_code: str | None
    students: int
    attempts: int
    average_score: float
    pass_rate: int
    last_attempt_at: ISODateTime | None


# ── Content ───────────────────────────────────────────────────────


class ExamItemOut(BaseModel):
    id: str
    title: str
    owner_id: str
    owner_email: str | None
    owner_name: str | None
    course_name: str | None
    is_shared: bool
    allow_practice: bool
    pass_grade: int
    time_limit_minutes: int | None
    total_questions: int
    created_at: ISODateTime


class ExamPageOut(BaseModel):
    items: list[ExamItemOut]
    total: int
    limit: int
    offset: int


class CourseItemOut(BaseModel):
    id: str
    name: str
    owner_id: str
    owner_email: str | None
    owner_name: str | None
    is_shared: bool
    created_at: ISODateTime


class CoursePageOut(BaseModel):
    items: list[CourseItemOut]
    total: int
    limit: int
    offset: int


class ContentUpdateIn(BaseModel):
    """Partial update for an exam or a course. Absent fields are untouched."""

    is_shared: bool | None = None
    owner_id: str | None = Field(default=None, max_length=ID_LENGTH)


# ── Audit log ─────────────────────────────────────────────────────


class AuditEntryOut(BaseModel):
    id: str
    # Null once the admin's account is deleted; `actor_email` is what keeps the
    # row readable after that.
    actor_id: str | None
    actor_email: str
    action: str
    target_type: str
    target_id: str | None
    target_label: str
    detail: dict
    created_at: ISODateTime


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    total: int
    limit: int
    offset: int


# ── Dashboard ─────────────────────────────────────────────────────


class PlatformOverviewOut(BaseModel):
    """Everything the admin landing page renders, in one request."""

    user_count: int
    student_count: int
    instructor_count: int
    admin_count: int
    # Accounts that registered but never chose a preferred name, so they are
    # stuck on onboarding and worth surfacing.
    pending_onboarding: int
    course_count: int
    exam_count: int
    attempts: int
    recent_attempts: int
    live_now: int
    average_score: float
    pass_rate: int
    total_seconds: int
    attempts_per_day: list[DailyPointOut]
    # Ten 10-point score bands, low to high. Always exactly ten entries.
    score_buckets: list[int]
    passed_count: int
    failed_count: int
    instructor_rollups: list[InstructorItemOut]
    topic_stats: list[TopicStatOut]


# ── System ────────────────────────────────────────────────────────


class TableCountsOut(BaseModel):
    users: int
    courses: int
    exams: int
    questions: int
    attempts: int
    in_progress: int
    audit_entries: int


class StorageStatOut(BaseModel):
    files: int
    bytes: int


class BackupInfoOut(BaseModel):
    """Reports on `./backups`, which compose mounts read-only into the API
    container. `available` is false when it is not mounted — the backup sidecar
    writes to a host directory, and a deployment may deliberately keep it out of
    this container."""

    available: bool
    files: int
    bytes: int
    latest_name: str | None
    latest_bytes: int | None
    latest_at: ISODateTime | None


class SystemInfoOut(BaseModel):
    environment: str
    # Whether /docs and /redoc are served, which follows from `environment`.
    api_docs_enabled: bool
    log_level: str
    postgres_version: str
    database_bytes: int
    counts: TableCountsOut
    uploads: StorageStatOut
    documents: StorageStatOut
    backups: BackupInfoOut
