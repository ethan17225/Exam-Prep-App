"""Platform administration: accounts, content, oversight and the audit log.

A cross-domain write view, one layer above `admin` (which is the instructor's
read view). Like that module it composes other domains' services rather than
importing their models, so every cross-user query stays in the domain that owns
the table. The one model it does import is its own — the audit log.

Authorization note: the functions here apply no per-caller predicate, because
there is none to apply. `require_admin` on the router *is* the boundary, unlike
the instructor analytics in `admin`, where the `instructor_id` filter inside each
query is the real gate and the route check is only the outer door.
"""

import pathlib
from datetime import datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.attempts import service as attempts_service
from src.auth import service as auth_service
from src.auth.constants import STAFF_ROLES, UserRole
from src.auth.models import User
from src.config import BASE_DIR, SHOW_DOCS_IN, settings
from src.courses import service as courses_service
from src.documents.config import documents_settings
from src.exams import service as exams_service
from src.identifiers import new_id
from src.platform_admin.constants import (
    ACTIVITY_DAYS,
    RECENT_DAYS,
    WEAK_TOPIC_LIMIT,
    AuditAction,
    TargetType,
)
from src.platform_admin.exceptions import (
    AccountNotFound,
    InstructorNotFound,
    OwnerNotStaff,
    ReassignToSameInstructor,
    SelfActionRefused,
    StudentHasNoInstructor,
)
from src.platform_admin.models import AdminAuditLog
from src.platform_admin.schemas import UserCreateIn, UserUpdateIn
from src.storage import remove_upload_files, storage_settings

# Compose mounts the backup sidecar's output here read-only. Absent on a
# deployment that keeps the dumps out of this container, which the system
# endpoint reports rather than treating as an error.
BACKUPS_DIR = BASE_DIR / "backups"

# Bounded like every other roster read: an instructor's student list on the user
# detail page is a panel, not a paginated table.
ROSTER_LIMIT = 100
RECENT_ATTEMPTS_LIMIT = 20


# ── Audit log ─────────────────────────────────────────────────────


async def record(
    actor: User,
    action: AuditAction,
    target_type: TargetType,
    target_id: str | None,
    target_label: str,
    db: AsyncSession,
    **detail,
) -> None:
    """Append one entry, and commit it.

    A second transaction after the action it describes, because the domain
    services commit their own work — so a crash between the two leaves the change
    applied and unlogged. Writing the log first would trade that for entries
    describing changes that never happened, which is the worse failure for an
    audit trail: a missing line is a gap, an invented one is misinformation.

    `actor_email` is copied in rather than joined on so the row survives the
    admin's own account being deleted.
    """
    db.add(
        AdminAuditLog(
            id=new_id(),
            actor_id=actor.id,
            actor_email=actor.email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            # Truncated to the column width: a label is a convenience copy, and a
            # 300-character exam title must not fail the write that records its
            # deletion.
            target_label=(target_label or "")[:255],
            detail=detail,
            created_at=datetime.now(),
        )
    )
    await db.commit()


async def list_audit(db: AsyncSession, action: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    filters = []
    if action:
        # Prefix match, so "user." selects every account action. This is why the
        # enum's values are `<target>.<verb>`.
        filters.append(AdminAuditLog.action.like(f"{action}%"))

    total = await db.scalar(select(func.count(AdminAuditLog.id)).where(*filters)) or 0
    stmt = (
        select(AdminAuditLog)
        .where(*filters)
        .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.execute(stmt)).scalars().all())
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ── Users ─────────────────────────────────────────────────────────


def _user_item(user: User, instructor_name: str | None, students: int, attempts: int, open_attempts: int) -> dict:
    """The one place UserItemOut's shape is assembled."""
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "display_name": user.display_name,
        "avatar": user.avatar,
        "invite_code": user.invite_code,
        "instructor_id": user.instructor_id,
        "instructor_name": instructor_name,
        "student_count": students,
        "attempts": attempts,
        "in_progress_count": open_attempts,
        "created_at": user.created_at,
    }


def _name_of(user: User | None) -> str | None:
    return (user.display_name or user.email) if user else None


async def _items_for(users: list[User], db: AsyncSession) -> list[dict]:
    """Decorate a page of accounts with their aggregates.

    Four batched queries for the whole page rather than four per row. The
    instructor lookup covers only the ids actually referenced, so a page of staff
    costs nothing extra.
    """
    if not users:
        return []

    instructor_ids = {u.instructor_id for u in users if u.instructor_id}
    instructors = await auth_service.users_by_ids(instructor_ids, db) if instructor_ids else {}
    rosters = await auth_service.student_counts_by_instructor(db)
    attempts = await attempts_service.attempt_counts_all(db)
    open_attempts = await attempts_service.in_progress_counts_all(db)

    return [
        _user_item(
            user,
            _name_of(instructors.get(user.instructor_id)) if user.instructor_id else None,
            rosters.get(user.id, 0),
            attempts.get(user.id, 0),
            open_attempts.get(user.id, 0),
        )
        for user in users
    ]


async def list_users(
    db: AsyncSession,
    query: str | None = None,
    role: UserRole | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    total = await auth_service.count_users(db, query, role)
    users = await auth_service.search_users(db, query, role, limit, offset)
    return {"items": await _items_for(users, db), "total": total, "limit": limit, "offset": offset}


async def _get_or_404(user_id: str, db: AsyncSession) -> User:
    user = await auth_service.get_by_id(user_id, db)
    if not user:
        raise AccountNotFound()
    return user


async def user_detail(user_id: str, db: AsyncSession) -> dict:
    user = await _get_or_404(user_id, db)

    # Sequential, not gathered: these share one AsyncSession, and concurrent
    # queries on a single session raise InterfaceError.
    items = await _items_for([user], db)
    rollup = await attempts_service.user_rollup(user_id, db)
    recent = await attempts_service.list_history_unscoped(user_id, db, RECENT_ATTEMPTS_LIMIT)
    owned_exams = await exams_service.count_all_unscoped(db, owner_id=user_id)
    owned_courses = await courses_service.count_all_unscoped(db, owner_id=user_id)

    roster: list[User] = []
    if user.role in STAFF_ROLES:
        roster = await auth_service.list_students(user_id, db, ROSTER_LIMIT)

    return {
        "user": items[0],
        "rollup": rollup,
        "owned_exams": owned_exams,
        "owned_courses": owned_courses,
        "students": await _items_for(roster, db),
        "recent_attempts": recent,
    }


async def _validated_instructor(instructor_id: str, db: AsyncSession) -> User:
    """An id that must name a real instructor.

    A student or admin id here would create an account enrolled with somebody
    who cannot own shared content or read a class page, which looks like data
    corruption rather than a mistake once it is stored.
    """
    instructor = await auth_service.get_by_id(instructor_id, db)
    if not instructor or instructor.role not in STAFF_ROLES:
        raise InstructorNotFound()
    return instructor


async def create_user(payload: UserCreateIn, actor: User, db: AsyncSession) -> dict:
    if payload.role is UserRole.STUDENT:
        if not payload.instructor_id:
            raise StudentHasNoInstructor()
        await _validated_instructor(payload.instructor_id, db)

    user = await auth_service.create_account(
        payload.email,
        payload.password,
        payload.role,
        payload.display_name,
        payload.instructor_id,
        db,
    )
    await record(
        actor,
        AuditAction.USER_CREATED,
        TargetType.USER,
        user.id,
        user.email,
        db,
        role=str(user.role),
    )
    return (await _items_for([user], db))[0]


async def update_user(user_id: str, payload: UserUpdateIn, actor: User, db: AsyncSession) -> dict:
    user = await _get_or_404(user_id, db)
    # model_fields_set distinguishes "absent" from "explicitly null": an explicit
    # null on instructor_id unenrols, while omitting it leaves the link alone.
    fields = payload.model_fields_set

    if "role" in fields and payload.role and payload.role != user.role:
        if user.id == actor.id:
            raise SelfActionRefused()
        previous = str(user.role)
        await auth_service.set_role(user, payload.role, db)
        await record(
            actor,
            AuditAction.USER_ROLE_CHANGED,
            TargetType.USER,
            user.id,
            user.email,
            db,
            **{"from": previous, "to": str(payload.role)},
        )

    if "instructor_id" in fields and payload.instructor_id != user.instructor_id:
        if payload.instructor_id:
            await _validated_instructor(payload.instructor_id, db)
        elif user.role == UserRole.STUDENT:
            # A student with no instructor belongs to nobody and disappears from
            # every class page, which is the state registration exists to prevent.
            raise StudentHasNoInstructor()
        await auth_service.set_instructor(user, payload.instructor_id, db)
        await record(
            actor,
            AuditAction.USER_INSTRUCTOR_CHANGED,
            TargetType.USER,
            user.id,
            user.email,
            db,
            instructor_id=payload.instructor_id,
        )

    if "display_name" in fields and payload.display_name:
        await auth_service.set_display_name(user, payload.display_name, db)

    return (await _items_for([user], db))[0]


async def reset_password(user_id: str, new_password: str, actor: User, db: AsyncSession) -> None:
    """Sets a new password and revokes every token the account holds.

    Deliberately allowed on the caller's own account: it is a sign-out-everywhere
    with a new password, and blocking it would only send them to the account page
    to do the same thing.
    """
    user = await _get_or_404(user_id, db)
    await auth_service.set_password(user, new_password, db)
    await record(actor, AuditAction.USER_PASSWORD_RESET, TargetType.USER, user.id, user.email, db)


async def revoke_sessions(user_id: str, actor: User, db: AsyncSession) -> None:
    user = await _get_or_404(user_id, db)
    await auth_service.revoke_tokens(user, db)
    await record(actor, AuditAction.USER_SESSIONS_REVOKED, TargetType.USER, user.id, user.email, db)


async def delete_user(user_id: str, actor: User, db: AsyncSession) -> None:
    """Delete an account and everything cascading from it.

    Refuses the caller's own account. That rule plus the same one on role changes
    is what guarantees an admin always exists, with no separate "last admin"
    counter to keep correct.
    """
    user = await _get_or_404(user_id, db)
    if user.id == actor.id:
        raise SelfActionRefused()

    email, role = user.email, str(user.role)
    # Collected before the cascade removes the question rows, or the files are
    # orphaned on the uploads volume with nothing left pointing at them.
    images = await exams_service.image_urls_for_owner_unscoped(user_id, db)
    await auth_service.delete_account(user, db)
    await run_in_threadpool(remove_upload_files, images)
    # `actor` is still attached: an admin cannot delete themselves, so the row
    # this writes can never reference an account that just disappeared.
    await record(actor, AuditAction.USER_DELETED, TargetType.USER, user_id, email, db, role=role)


# ── Instructors ───────────────────────────────────────────────────


async def list_instructors(db: AsyncSession) -> list[dict]:
    """Instructors with their class aggregates, plus the enrolment code each one needs.

    The code comes from the roster query rather than the rollups: an admin
    managing sign-ups needs it for instructors who have no students yet, which is
    exactly the row a history-driven query would omit.
    """
    rollups = await attempts_service.instructor_rollups(db)
    staff = await auth_service.list_staff(db)
    codes = {user.id: user.invite_code for user in staff}
    return [{**row, "invite_code": codes.get(row["instructor_id"])} for row in rollups]


async def rotate_invite_code(user_id: str, actor: User, db: AsyncSession) -> str:
    """Mint a fresh enrolment code for one instructor.

    Students already enrolled keep their link: `instructor_id` is the link, and
    the code is only the gate that created it. Rotating is therefore how a leaked
    code is closed without disrupting a class.
    """
    user = await _get_or_404(user_id, db)
    if user.role not in STAFF_ROLES:
        raise InstructorNotFound()

    await auth_service.rotate_invite_code(user, db)
    await record(actor, AuditAction.INVITE_CODE_ROTATED, TargetType.USER, user.id, user.email, db)
    return user.invite_code


async def reassign_students(from_id: str, to_instructor_id: str, actor: User, db: AsyncSession) -> int:
    if from_id == to_instructor_id:
        raise ReassignToSameInstructor()

    source = await _get_or_404(from_id, db)
    if source.role not in STAFF_ROLES:
        raise InstructorNotFound()
    target = await _validated_instructor(to_instructor_id, db)

    moved = await auth_service.reassign_students(from_id, to_instructor_id, db)
    await record(
        actor,
        AuditAction.STUDENTS_REASSIGNED,
        TargetType.USER,
        from_id,
        source.email,
        db,
        to_instructor_id=to_instructor_id,
        to_instructor_email=target.email,
        moved=moved,
    )
    return moved


# ── Content ───────────────────────────────────────────────────────


async def _owner_lookup(owner_ids, db: AsyncSession) -> dict[str, User]:
    return await auth_service.users_by_ids({owner_id for owner_id in owner_ids if owner_id}, db)


async def list_exams(
    db: AsyncSession,
    query: str | None = None,
    owner_id: str | None = None,
    shared: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    total = await exams_service.count_all_unscoped(db, query, owner_id, shared)
    exams = await exams_service.list_all_unscoped(db, query, owner_id, shared, limit, offset)
    counts = await exams_service.question_counts_by_exam_ids([e.id for e in exams], db)
    owners = await _owner_lookup([e.owner_id for e in exams], db)

    items = [
        {
            "id": exam.id,
            "title": exam.title,
            "owner_id": exam.owner_id,
            "owner_email": owners[exam.owner_id].email if exam.owner_id in owners else None,
            "owner_name": _name_of(owners.get(exam.owner_id)),
            # Eager-loaded by the listing query, so this costs nothing.
            "course_name": exam.course.name if exam.course else None,
            "is_shared": exam.is_shared,
            "allow_practice": exam.allow_practice,
            "pass_grade": exam.pass_grade,
            "time_limit_minutes": exam.time_limit_minutes,
            "total_questions": counts.get(exam.id, 0),
            "created_at": exam.created_at,
        }
        for exam in exams
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def list_courses(
    db: AsyncSession,
    query: str | None = None,
    owner_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    total = await courses_service.count_all_unscoped(db, query, owner_id)
    courses = await courses_service.list_all_unscoped(db, query, owner_id, limit, offset)
    owners = await _owner_lookup([c.owner_id for c in courses], db)

    items = [
        {
            "id": course.id,
            "name": course.name,
            "owner_id": course.owner_id,
            "owner_email": owners[course.owner_id].email if course.owner_id in owners else None,
            "owner_name": _name_of(owners.get(course.owner_id)),
            "is_shared": course.is_shared,
            "created_at": course.created_at,
        }
        for course in courses
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def _validated_content_owner(owner_id: str, db: AsyncSession) -> User:
    """A transfer target has to be an instructor.

    Visibility is frozen at creation, so a student or admin owner can never
    publish; moving shared material to one would leave it shared in the column
    and unreachable in practice for everybody who could previously see it.
    """
    owner = await auth_service.get_by_id(owner_id, db)
    if not owner:
        raise AccountNotFound()
    if owner.role not in STAFF_ROLES:
        raise OwnerNotStaff()
    return owner


async def update_exam(
    exam_id: str, is_shared: bool | None, owner_id: str | None, actor: User, db: AsyncSession
) -> None:
    exam = await exams_service.get_or_404_unscoped(exam_id, db)

    if owner_id is not None and owner_id != exam.owner_id:
        owner = await _validated_content_owner(owner_id, db)
        await exams_service.transfer_owner_unscoped(exam, owner_id, db)
        await record(
            actor,
            AuditAction.EXAM_TRANSFERRED,
            TargetType.EXAM,
            exam.id,
            exam.title,
            db,
            owner_id=owner_id,
            owner_email=owner.email,
        )

    if is_shared is not None and is_shared is not exam.is_shared:
        await exams_service.set_shared_unscoped(exam, is_shared, db)
        await record(
            actor,
            AuditAction.EXAM_SHARING_CHANGED,
            TargetType.EXAM,
            exam.id,
            exam.title,
            db,
            is_shared=is_shared,
        )


async def delete_exam(exam_id: str, actor: User, db: AsyncSession) -> None:
    exam = await exams_service.get_or_404_unscoped(exam_id, db)
    title = exam.title
    await exams_service.delete_unscoped(exam, db)
    await record(actor, AuditAction.EXAM_DELETED, TargetType.EXAM, exam_id, title, db)


async def update_course(
    course_id: str, is_shared: bool | None, owner_id: str | None, actor: User, db: AsyncSession
) -> None:
    course = await courses_service.get_or_404_unscoped(course_id, db)

    if owner_id is not None and owner_id != course.owner_id:
        owner = await _validated_content_owner(owner_id, db)
        await courses_service.transfer_owner_unscoped(course, owner_id, db)
        await record(
            actor,
            AuditAction.COURSE_TRANSFERRED,
            TargetType.COURSE,
            course.id,
            course.name,
            db,
            owner_id=owner_id,
            owner_email=owner.email,
        )

    if is_shared is not None and is_shared is not course.is_shared:
        await courses_service.set_shared_unscoped(course, is_shared, db)
        await record(
            actor,
            AuditAction.COURSE_SHARING_CHANGED,
            TargetType.COURSE,
            course.id,
            course.name,
            db,
            is_shared=is_shared,
        )


async def delete_course(course_id: str, actor: User, db: AsyncSession) -> None:
    course = await courses_service.get_or_404_unscoped(course_id, db)
    name = course.name
    await courses_service.delete_unscoped(course, db)
    await record(actor, AuditAction.COURSE_DELETED, TargetType.COURSE, course_id, name, db)


# ── Monitoring ────────────────────────────────────────────────────


async def reset_attempt(record_id: str, actor: User, db: AsyncSession) -> None:
    """Discard anyone's open attempt, and log who did it.

    The audit entry is the only thing separating this from the instructor route
    that deletes the same row. Discarding an attempt destroys the answers a
    student has entered, so the one surface where that is done to a stranger
    should say who did it — hence reading the record before deleting, purely so
    the entry can name the exam and the student rather than an opaque id.
    """
    attempt = await attempts_service.get_in_progress_unscoped_or_404(record_id, db)
    exam_title = attempt.exam_title
    student_id = attempt.user_id
    student_email = attempt.user.email if attempt.user else None
    mode = str(attempt.mode)

    await attempts_service.reset_attempt_unscoped(record_id, db)
    await record(
        actor,
        AuditAction.ATTEMPT_RESET,
        TargetType.ATTEMPT,
        record_id,
        exam_title,
        db,
        student_id=student_id,
        student_email=student_email,
        mode=mode,
    )


# ── Dashboard ─────────────────────────────────────────────────────


async def build_overview(db: AsyncSession) -> dict:
    """Everything the admin landing page needs, in one request.

    Sequential rather than gathered, for the same reason as the instructor
    overview: one AsyncSession cannot serve concurrent queries.
    """
    roles = await auth_service.role_counts(db)
    total_users = sum(roles.values())
    pending = await auth_service.count_pending_onboarding(db)

    totals = await attempts_service.platform_totals(RECENT_DAYS, db)
    live_now = await attempts_service.count_in_progress_all(db)
    per_day = await attempts_service.platform_attempts_per_day(ACTIVITY_DAYS, db)
    buckets = await attempts_service.platform_score_buckets(db)
    topics = await attempts_service.platform_topic_stats(db)
    rollups = await list_instructors(db)
    exam_count = await exams_service.count_all(db)
    course_count = await courses_service.count_all(db)

    attempts = totals["attempts"]
    return {
        "user_count": total_users,
        "student_count": roles.get(UserRole.STUDENT, 0),
        "instructor_count": roles.get(UserRole.INSTRUCTOR, 0),
        "admin_count": roles.get(UserRole.ADMIN, 0),
        "pending_onboarding": pending,
        "course_count": course_count,
        "exam_count": exam_count,
        "attempts": attempts,
        "recent_attempts": totals["recent_attempts"],
        "live_now": live_now,
        "average_score": totals["average_score"],
        "pass_rate": totals["pass_rate"],
        "total_seconds": totals["total_seconds"],
        "attempts_per_day": per_day,
        "score_buckets": buckets,
        "passed_count": totals["passed_count"],
        "failed_count": attempts - totals["passed_count"],
        "instructor_rollups": rollups,
        # Weakest first: the API sorts strongest-first for the student's own
        # chart, and an admin cares about where the deployment is struggling.
        "topic_stats": list(reversed(topics))[:WEAK_TOPIC_LIMIT],
    }


# ── System ────────────────────────────────────────────────────────


async def build_system_info(db: AsyncSession) -> dict:
    """A snapshot of the deployment: row counts, database size and disk usage.

    The counts query is the one place in the app outside a domain service that
    names tables directly. Splitting seven `SELECT COUNT(*)`s across six domains
    would add six functions with no authorization logic to carry — the rule those
    functions exist for is about per-user scoping, and a table-wide row count has
    none to get wrong.
    """
    row = (
        await db.execute(
            text(
                """
                SELECT (SELECT COUNT(*) FROM "user") AS users,
                       (SELECT COUNT(*) FROM course) AS courses,
                       (SELECT COUNT(*) FROM exam) AS exams,
                       (SELECT COUNT(*) FROM question) AS questions,
                       (SELECT COUNT(*) FROM history) AS attempts,
                       (SELECT COUNT(*) FROM in_progress_exam) AS in_progress,
                       (SELECT COUNT(*) FROM admin_audit_log) AS audit_entries,
                       pg_database_size(current_database()) AS database_bytes,
                       current_setting('server_version') AS postgres_version
                """
            )
        )
    ).one()

    # One threadpool hop per directory for the whole walk, not one per file.
    uploads = await run_in_threadpool(_directory_stat, storage_settings.dir)
    documents = await run_in_threadpool(_directory_stat, documents_settings.root)
    backups = await run_in_threadpool(_backup_info)

    return {
        "environment": settings.environment,
        "api_docs_enabled": settings.environment in SHOW_DOCS_IN,
        "log_level": settings.log_level,
        "postgres_version": row.postgres_version,
        "database_bytes": int(row.database_bytes),
        "counts": {
            "users": row.users,
            "courses": row.courses,
            "exams": row.exams,
            "questions": row.questions,
            "attempts": row.attempts,
            "in_progress": row.in_progress,
            "audit_entries": row.audit_entries,
        },
        "uploads": uploads,
        "documents": documents,
        "backups": backups,
    }


def _directory_stat(root: pathlib.Path) -> dict:
    """File count and total bytes under `root`. Fully synchronous so the caller
    can hand the whole walk to one `run_in_threadpool` call."""
    files = 0
    total = 0
    if not root.is_dir():
        return {"files": 0, "bytes": 0}
    for path in root.rglob("*"):
        # A file that vanishes mid-walk (the backup sidecar prunes on a timer) must
        # not turn a status page into a 500.
        try:
            if path.is_file():
                files += 1
                total += path.stat().st_size
        except OSError:
            continue
    return {"files": files, "bytes": total}


def _backup_info() -> dict:
    """What the backup sidecar has produced, read from the read-only mount.

    Names, sizes and timestamps only — never contents. The dumps hold every
    password hash and answer key in the deployment, so nothing here opens one.
    """
    empty = {
        "available": False,
        "files": 0,
        "bytes": 0,
        "latest_name": None,
        "latest_bytes": None,
        "latest_at": None,
    }
    if not BACKUPS_DIR.is_dir():
        return empty

    entries = []
    for path in BACKUPS_DIR.glob("*.sql.gz"):
        try:
            entries.append((path.name, path.stat()))
        except OSError:
            continue

    if not entries:
        return {**empty, "available": True}

    name, stat = max(entries, key=lambda pair: pair[1].st_mtime)
    return {
        "available": True,
        "files": len(entries),
        "bytes": sum(item[1].st_size for item in entries),
        "latest_name": name,
        "latest_bytes": stat.st_size,
        "latest_at": datetime.fromtimestamp(stat.st_mtime),
    }
