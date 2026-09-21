from enum import StrEnum


class AuditAction(StrEnum):
    """What an admin did. Stored as the string, not an id, so a log row is
    readable in `psql` without a join — and a value retired from this enum keeps
    rendering rather than becoming an orphan reference.

    `<target>.<verb>` keeps the log filterable by area with a prefix match.
    """

    USER_CREATED = "user.created"
    USER_ROLE_CHANGED = "user.role_changed"
    USER_INSTRUCTOR_CHANGED = "user.instructor_changed"
    USER_PASSWORD_RESET = "user.password_reset"
    USER_SESSIONS_REVOKED = "user.sessions_revoked"
    USER_DELETED = "user.deleted"
    INVITE_CODE_ROTATED = "instructor.code_rotated"
    STUDENTS_REASSIGNED = "instructor.students_reassigned"
    EXAM_SHARING_CHANGED = "exam.sharing_changed"
    EXAM_TRANSFERRED = "exam.transferred"
    EXAM_DELETED = "exam.deleted"
    COURSE_SHARING_CHANGED = "course.sharing_changed"
    COURSE_TRANSFERRED = "course.transferred"
    COURSE_DELETED = "course.deleted"
    ATTEMPT_RESET = "attempt.reset"


class TargetType(StrEnum):
    USER = "user"
    EXAM = "exam"
    COURSE = "course"
    ATTEMPT = "attempt"


# The prefixes `AuditAction` uses, which the audit page turns into filter chips.
#
# Not the same list as TargetType, and deliberately so: rotating a code or moving
# a roster targets a `user` row but belongs under "instructor" in the log, because
# that is the area an admin would look in. A new prefix with no chip would be
# reachable only under "All", so the test that pins this set is what keeps the two
# from drifting apart.
AUDIT_AREAS = frozenset({"user", "instructor", "exam", "course", "attempt"})


# Matched to `admin.service` so that "last 14 days" and "last 30 days" mean the
# same thing on the platform dashboard as on an instructor's.
ACTIVITY_DAYS = 14
RECENT_DAYS = 30

# Page size ceiling for the listing endpoints. They return whole rows rather
# than aggregates, so this is the thing standing between one query string and a
# multi-megabyte response.
MAX_PAGE_SIZE = 100

# How many of the deployment's weakest topics the dashboard charts.
WEAK_TOPIC_LIMIT = 8
