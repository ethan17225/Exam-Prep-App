"""The admin surface.

Mounted at `/api/platform` rather than `/api/admin`, which is the *instructor*
analytics surface and has been since before this role existed. Two prefixes with
two different gates is the point: every route under `/api/admin` is satisfied by
an instructor, and every route here demands an admin. Reusing one prefix for both
would mean reading each decorator to know which.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.attempts.exceptions import RecordNotFound
from src.auth import service as auth_service
from src.auth.constants import UserRole
from src.auth.dependencies import AdminDep, CurrentUserDep, ImpersonationActorDep, require_admin
from src.auth.exceptions import AdminRequired, EmailTaken
from src.auth.schemas import TokenOut
from src.courses.exceptions import CourseNameTaken, CourseNotFound
from src.database import SessionDep
from src.exams.exceptions import ExamNotFound
from src.platform_admin import service
from src.platform_admin.constants import MAX_PAGE_SIZE
from src.platform_admin.exceptions import (
    AccountNotFound,
    AlreadyImpersonating,
    ImpersonateAdminRefused,
    ImpersonateSelfRefused,
    InstructorNotFound,
    NotImpersonating,
    OwnerNotStaff,
    ReassignToSameInstructor,
    SelfActionRefused,
    StudentHasNoInstructor,
)
from src.platform_admin.schemas import (
    SEARCH_MAX,
    AuditPageOut,
    ContentUpdateIn,
    CoursePageOut,
    ExamPageOut,
    InstructorItemOut,
    InviteCodeOut,
    PasswordResetIn,
    PlatformOverviewOut,
    ReassignedOut,
    ReassignIn,
    RevokedOut,
    SystemInfoOut,
    UpdatedOut,
    UserCreateIn,
    UserDetailOut,
    UserItemOut,
    UserPageOut,
    UserUpdateIn,
)
from src.schemas import DeletedOut

router = APIRouter(prefix="/api/platform", tags=["platform-admin"])

# Every route in this file is admin-only, so the gate is declared once here
# rather than repeated per decorator. Routes that need the identity — anything
# audited, or anything that must refuse to act on the caller's own account —
# still take `user: AdminDep` and get the same dependency resolved once.
FORBIDDEN = {status.HTTP_403_FORBIDDEN: {"description": AdminRequired.DETAIL}}
NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": AccountNotFound.DETAIL}}

SearchQuery = Annotated[str | None, Query(max_length=SEARCH_MAX)]
LimitQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
OffsetQuery = Annotated[int, Query(ge=0)]


# ── Dashboard ─────────────────────────────────────────────────────


@router.get(
    "/overview",
    response_model=PlatformOverviewOut,
    summary="Platform overview",
    description=(
        "Deployment-wide aggregates: account counts by role, content totals, 14 "
        "days of activity, the score distribution, per-instructor rollups and the "
        "weakest topics. Unlike /api/admin/overview nothing here is scoped to one "
        "instructor's students."
    ),
    dependencies=[Depends(require_admin)],
    responses=FORBIDDEN,
)
async def platform_overview(db: SessionDep):
    return await service.build_overview(db)


# ── Users ─────────────────────────────────────────────────────────


@router.get(
    "/users",
    response_model=UserPageOut,
    summary="List accounts",
    description=(
        "Every account, newest first, with its aggregates. `q` matches email or "
        "preferred name; `role` filters exactly. Paginated because this returns "
        "rows rather than aggregates."
    ),
    dependencies=[Depends(require_admin)],
    responses=FORBIDDEN,
)
async def list_users(
    db: SessionDep,
    q: SearchQuery = None,
    role: UserRole | None = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
):
    return await service.list_users(db, q, role, limit, offset)


@router.post(
    "/users",
    response_model=UserItemOut,
    summary="Create an account",
    description=(
        "Mints an account of any role, including another admin — the admin gate "
        "replaces the invite code that public registration requires, and this is "
        "the only path that can create an admin. Supplying `display_name` lets the "
        "account skip onboarding. A student requires a valid `instructor_id`."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_404_NOT_FOUND: {"description": InstructorNotFound.DETAIL},
        status.HTTP_409_CONFLICT: {"description": EmailTaken.DETAIL},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": StudentHasNoInstructor.DETAIL},
    },
)
async def create_user(payload: UserCreateIn, user: AdminDep, db: SessionDep):
    return await service.create_user(payload, user, db)


@router.get(
    "/users/{user_id}",
    response_model=UserDetailOut,
    summary="One account's detail",
    description=(
        "Profile, aggregates, how much content the account owns, its recent "
        "attempts, and — for an instructor or admin — the roster enrolled with it."
    ),
    dependencies=[Depends(require_admin)],
    responses={**FORBIDDEN, **NOT_FOUND},
)
async def user_detail(user_id: str, db: SessionDep):
    return await service.user_detail(user_id, db)


@router.patch(
    "/users/{user_id}",
    response_model=UserItemOut,
    summary="Update an account",
    description=(
        "Changes role, preferred name or enrolment. Changing a role revokes every "
        "token the account holds, so the nav it renders cannot lag behind its "
        "permissions. An admin may not change their own role — that rule is what "
        "guarantees an admin always exists."
    ),
    responses={
        **FORBIDDEN,
        **NOT_FOUND,
        status.HTTP_409_CONFLICT: {"description": SelfActionRefused.DETAIL},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": StudentHasNoInstructor.DETAIL},
    },
)
async def update_user(user_id: str, payload: UserUpdateIn, user: AdminDep, db: SessionDep):
    return await service.update_user(user_id, payload, user, db)


@router.post(
    "/users/{user_id}/password",
    response_model=RevokedOut,
    summary="Reset an account's password",
    description=(
        "Sets a new password without needing the old one, and revokes every "
        "existing token for that account. Allowed on your own account, where it "
        "behaves as a password change plus sign-out-everywhere."
    ),
    responses={**FORBIDDEN, **NOT_FOUND},
)
async def reset_password(user_id: str, payload: PasswordResetIn, user: AdminDep, db: SessionDep) -> RevokedOut:
    await service.reset_password(user_id, payload.new_password, user, db)
    return RevokedOut(revoked=True)


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=RevokedOut,
    summary="Sign an account out everywhere",
    description=(
        "Bumps the account's token version, which kills every outstanding bearer "
        "token immediately. The only way to cut short a stolen 12-hour JWT without "
        "changing the password."
    ),
    responses={**FORBIDDEN, **NOT_FOUND},
)
async def revoke_sessions(user_id: str, user: AdminDep, db: SessionDep) -> RevokedOut:
    await service.revoke_sessions(user_id, user, db)
    return RevokedOut(revoked=True)


@router.post(
    "/users/{user_id}/impersonate",
    response_model=TokenOut,
    summary="Impersonate an account",
    description=(
        "Starts a full act-as session as the target student or instructor. The "
        "returned token carries the target as the effective identity and the "
        "calling admin in an `act` claim, so platform routes remain available. "
        "Audited. Refuses self, other admins, and nested impersonation."
    ),
    responses={
        **FORBIDDEN,
        **NOT_FOUND,
        status.HTTP_409_CONFLICT: {
            "description": (
                f"{ImpersonateSelfRefused.DETAIL} / {AlreadyImpersonating.DETAIL}"
            )
        },
    },
)
async def impersonate_user(
    user_id: str,
    user: AdminDep,
    actor: ImpersonationActorDep,
    db: SessionDep,
):
    target = await service.start_impersonation(
        user_id,
        user,
        db,
        already_impersonating=actor is not None,
    )
    return auth_service.impersonation_login_response(user, target)


@router.post(
    "/impersonate/end",
    response_model=TokenOut,
    summary="End impersonation",
    description=(
        "Ends the current impersonation session and returns a fresh normal token "
        "for the real admin. Audited. Requires an active impersonation bearer."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_409_CONFLICT: {"description": NotImpersonating.DETAIL},
    },
)
async def end_impersonation(
    user: AdminDep,
    effective: CurrentUserDep,
    actor: ImpersonationActorDep,
    db: SessionDep,
):
    admin = await service.end_impersonation(
        user,
        effective,
        db,
        is_impersonating=actor is not None,
    )
    return auth_service.login_response(admin)


@router.delete(
    "/users/{user_id}",
    response_model=DeletedOut,
    summary="Delete an account",
    description=(
        "Removes the account and everything cascading from it: its courses, exams "
        "and questions, its attempt history and any open attempt. Students of a "
        "deleted instructor are unenrolled, not deleted. Refuses your own account."
    ),
    responses={
        **FORBIDDEN,
        **NOT_FOUND,
        status.HTTP_409_CONFLICT: {"description": SelfActionRefused.DETAIL},
    },
)
async def delete_user(user_id: str, user: AdminDep, db: SessionDep) -> DeletedOut:
    await service.delete_user(user_id, user, db)
    return DeletedOut(deleted=True)


# ── Instructors ───────────────────────────────────────────────────
#
# Fixed paths before parameterized siblings, or "instructors" is captured as a
# user id and the route 404s silently.


@router.get(
    "/instructors",
    response_model=list[InstructorItemOut],
    summary="List instructors",
    description=(
        "Every instructor and admin with their roster size, class aggregates and "
        "enrolment code. Driven from the account list, so somebody who has not "
        "enrolled anybody yet still appears with zeros."
    ),
    dependencies=[Depends(require_admin)],
    responses=FORBIDDEN,
)
async def list_instructors(db: SessionDep):
    return await service.list_instructors(db)


@router.post(
    "/instructors/{user_id}/rotate-code",
    response_model=InviteCodeOut,
    summary="Rotate an enrolment code",
    description=(
        "Issues a fresh personal enrolment code. Students already enrolled keep "
        "their link — `instructor_id` is the link and the code is only the gate "
        "that created it — so this closes a leaked code without disrupting a class."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_404_NOT_FOUND: {"description": InstructorNotFound.DETAIL},
    },
)
async def rotate_invite_code(user_id: str, user: AdminDep, db: SessionDep) -> InviteCodeOut:
    return InviteCodeOut(invite_code=await service.rotate_invite_code(user_id, user, db))


@router.post(
    "/instructors/{user_id}/reassign-students",
    response_model=ReassignedOut,
    summary="Move a whole roster",
    description=(
        "Re-enrols every student of one instructor with another, returning how "
        "many moved. For an instructor leaving — without it their students are "
        "unenrolled by the delete and belong to nobody."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_404_NOT_FOUND: {"description": InstructorNotFound.DETAIL},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": ReassignToSameInstructor.DETAIL},
    },
)
async def reassign_students(user_id: str, payload: ReassignIn, user: AdminDep, db: SessionDep) -> ReassignedOut:
    moved = await service.reassign_students(user_id, payload.to_instructor_id, user, db)
    return ReassignedOut(moved=moved)


# ── Content ───────────────────────────────────────────────────────


@router.get(
    "/exams",
    response_model=ExamPageOut,
    summary="List every exam",
    description=(
        "All exams regardless of owner or sharing, newest first, each with its "
        "owner and question count. `/api/exams` applies the visibility predicate; "
        "this deliberately does not, which is what makes it the moderation view."
    ),
    dependencies=[Depends(require_admin)],
    responses=FORBIDDEN,
)
async def list_exams(
    db: SessionDep,
    q: SearchQuery = None,
    owner_id: Annotated[str | None, Query(max_length=64)] = None,
    shared: bool | None = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
):
    return await service.list_exams(db, q, owner_id, shared, limit, offset)


@router.patch(
    "/exams/{exam_id}",
    response_model=UpdatedOut,
    summary="Moderate an exam",
    description=(
        "Sets sharing or transfers ownership. Sharing is frozen at creation "
        "everywhere else — this is the only route that can unpublish something "
        "already shared. A transfer target must be an instructor or an admin, "
        "since a student owner can never publish."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_404_NOT_FOUND: {"description": ExamNotFound.DETAIL},
        status.HTTP_409_CONFLICT: {"description": OwnerNotStaff.DETAIL},
    },
)
async def update_exam(exam_id: str, payload: ContentUpdateIn, user: AdminDep, db: SessionDep) -> UpdatedOut:
    await service.update_exam(exam_id, payload.is_shared, payload.owner_id, user, db)
    return UpdatedOut(updated=True)


@router.delete(
    "/exams/{exam_id}",
    response_model=DeletedOut,
    summary="Delete any exam",
    description=(
        "Deletes an exam owned by anyone, with its questions and their uploaded "
        "images. Attempt history survives: `history.exam_id` has no foreign key "
        "precisely so a deleted exam does not erase the marks awarded for it."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_404_NOT_FOUND: {"description": ExamNotFound.DETAIL},
    },
)
async def delete_exam(exam_id: str, user: AdminDep, db: SessionDep) -> DeletedOut:
    await service.delete_exam(exam_id, user, db)
    return DeletedOut(deleted=True)


@router.get(
    "/courses",
    response_model=CoursePageOut,
    summary="List every course",
    description="All courses regardless of owner or sharing, newest first.",
    dependencies=[Depends(require_admin)],
    responses=FORBIDDEN,
)
async def list_courses(
    db: SessionDep,
    q: SearchQuery = None,
    owner_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
):
    return await service.list_courses(db, q, owner_id, limit, offset)


@router.patch(
    "/courses/{course_id}",
    response_model=UpdatedOut,
    summary="Moderate a course",
    description=(
        "Sets sharing or transfers ownership. Course names are unique per owner, "
        "so a transfer to somebody who already has a course of that name is a 409 "
        "rather than a driver error."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_404_NOT_FOUND: {"description": CourseNotFound.DETAIL},
        status.HTTP_409_CONFLICT: {"description": f"{OwnerNotStaff.DETAIL} / {CourseNameTaken.DETAIL}"},
    },
)
async def update_course(course_id: str, payload: ContentUpdateIn, user: AdminDep, db: SessionDep) -> UpdatedOut:
    await service.update_course(course_id, payload.is_shared, payload.owner_id, user, db)
    return UpdatedOut(updated=True)


@router.delete(
    "/courses/{course_id}",
    response_model=DeletedOut,
    summary="Delete any course",
    description=(
        "Deletes a course owned by anyone. Its exams survive and become unfiled — "
        "`exam.course_id` is ON DELETE SET NULL."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_404_NOT_FOUND: {"description": CourseNotFound.DETAIL},
    },
)
async def delete_course(course_id: str, user: AdminDep, db: SessionDep) -> DeletedOut:
    await service.delete_course(course_id, user, db)
    return DeletedOut(deleted=True)


# ── Monitoring ────────────────────────────────────────────────────


@router.delete(
    "/in-progress/{record_id}",
    response_model=DeletedOut,
    summary="Reset any open attempt",
    description=(
        "The audited twin of DELETE /api/admin/in-progress/{id}. Both clear the "
        "same row; only this one names who did it in the audit log. An admin does "
        "not pass the instructor gate, so this is the only reset they can call."
    ),
    responses={
        **FORBIDDEN,
        status.HTTP_404_NOT_FOUND: {"description": RecordNotFound.DETAIL},
    },
)
async def reset_attempt(record_id: str, user: AdminDep, db: SessionDep) -> DeletedOut:
    await service.reset_attempt(record_id, user, db)
    return DeletedOut(deleted=True)


# ── Audit log ─────────────────────────────────────────────────────


@router.get(
    "/audit",
    response_model=AuditPageOut,
    summary="Read the audit log",
    description=(
        "Every mutating admin action, newest first. `action` is a prefix match, so "
        "`user.` selects all account actions and `user.deleted` just the deletions. "
        "Append-only: no route updates or removes an entry."
    ),
    dependencies=[Depends(require_admin)],
    responses=FORBIDDEN,
)
async def list_audit(
    db: SessionDep,
    action: Annotated[str | None, Query(max_length=40)] = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
):
    return await service.list_audit(db, action, limit, offset)


# ── System ────────────────────────────────────────────────────────


@router.get(
    "/system",
    response_model=SystemInfoOut,
    summary="Deployment status",
    description=(
        "Environment, Postgres version, database size, row counts and disk usage "
        "for the uploads and documents volumes, plus what the backup sidecar has "
        "written. Backup files are reported by name, size and time only — the "
        "dumps hold every password hash in the deployment, so nothing reads one."
    ),
    dependencies=[Depends(require_admin)],
    responses=FORBIDDEN,
)
async def system_info(db: SessionDep):
    return await service.build_system_info(db)
