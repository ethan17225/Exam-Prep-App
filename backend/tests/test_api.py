"""HTTP-level checks that need no database and no running server.

Two things must never regress silently: every route requiring a session, and bad
input producing a 422 rather than a 500 (a 500 on submit costs a student their
completed attempt). Ownership behaviour needs real rows — that lives in
test_e2e.py.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx2 import AsyncClient
from pydantic import ValidationError

from src.attempts.router import history_router, progress_router
from src.attempts.schemas import HistorySummaryOut
from src.auth import service as auth_service
from src.auth.config import auth_settings
from src.auth.constants import REGISTRABLE_ROLES, STAFF_ROLES, UserRole
from src.auth.dependencies import get_current_user, require_admin, require_instructor
from src.auth.exceptions import InstructorRequired, InvalidInviteCode, RegistrationClosed
from src.auth.schemas import RegisterIn
from src.constants import MAX_QUESTIONS_PER_EXAM
from src.exams.exceptions import EmptyTitle, ExamNotFound, QuestionNotFound
from src.exams.router import router as exams_router
from src.exams.schemas import ExamFromBank
from src.exams.service import allocate_section_draws
from src.grading.service import grade_question
from src.identifiers import ID_LENGTH, new_id
from src.main import app
from src.platform_admin import service as platform_service
from src.platform_admin.constants import AUDIT_AREAS, AuditAction
from src.platform_admin.exceptions import (
    AlreadyImpersonating,
    ImpersonateAdminRefused,
    ImpersonateSelfRefused,
    NotImpersonating,
)
from src.storage import ALLOWED_IMAGE_EXTENSIONS

SRC = Path(__file__).resolve().parent.parent / "src"

ANONYMOUS_GET_PATHS = [
    "/api/exams",
    "/api/courses",
    "/api/question-banks",
    "/api/history",
    "/api/history/topic-stats",
    "/api/in-progress",
    "/api/admin/dashboard",
    "/api/admin/overview",
    "/api/admin/students",
    "/api/admin/students/u1",
    "/api/platform/overview",
    "/api/platform/users",
    "/api/platform/users/u1",
    "/api/platform/instructors",
    "/api/platform/exams",
    "/api/platform/courses",
    "/api/platform/audit",
    "/api/platform/system",
    "/api/documents",
    "/api/auth/me",
    # StaticFiles mounts: dependencies do not apply to them, so these prove the
    # middleware guard is in place.
    "/docs-files/anything.pdf",
    "/api/uploads/anything.png",
]


@pytest.mark.parametrize("path", ANONYMOUS_GET_PATHS)
async def test_anonymous_get_is_rejected(anon: AsyncClient, path: str):
    assert (await anon.get(path)).status_code == 401


async def test_anonymous_mutations_are_rejected(anon: AsyncClient):
    assert (await anon.post("/api/exams/abc/submit", json={})).status_code == 401
    assert (await anon.delete("/api/exams/abc")).status_code == 401
    assert (await anon.post("/api/in-progress", json={})).status_code == 401
    assert (await anon.post("/api/question-banks", json={"title": "x"})).status_code == 401
    assert (
        await anon.post(
            "/api/exams/from-bank",
            json={
                "title": "x",
                "bank_id": "b" * 12,
                "shares": [{"section_id": "s" * 12, "percent": 50}],
                "questions_per_attempt": 10,
                "pass_grade": 72,
            },
        )
    ).status_code == 401


async def test_garbage_token_is_rejected(anon: AsyncClient):
    resp = await anon.get("/api/exams", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/dashboard",
        "/api/admin/overview",
        "/api/admin/students",
        "/api/admin/students/u9",
        "/api/question-banks",
    ],
)
async def test_student_is_blocked_from_instructor_routes(as_student: AsyncClient, path: str):
    assert (await as_student.get(path)).status_code == 403


# ── The admin gate ─────────────────────────────────────────────────

PLATFORM_GET_PATHS = [
    "/api/platform/overview",
    "/api/platform/users",
    "/api/platform/users/u9",
    "/api/platform/instructors",
    "/api/platform/exams",
    "/api/platform/courses",
    "/api/platform/audit",
    "/api/platform/system",
]

PLATFORM_MUTATIONS = [
    ("post", "/api/platform/users", {"email": "a@b.co", "password": "password1", "role": "admin"}),
    ("patch", "/api/platform/users/u9", {"role": "admin"}),
    ("post", "/api/platform/users/u9/password", {"new_password": "password1"}),
    ("post", "/api/platform/users/u9/revoke-sessions", {}),
    ("post", "/api/platform/users/u9/impersonate", {}),
    ("post", "/api/platform/impersonate/end", {}),
    ("delete", "/api/platform/users/u9", None),
    ("post", "/api/platform/instructors/u9/rotate-code", {}),
    ("post", "/api/platform/instructors/u9/reassign-students", {"to_instructor_id": "u2"}),
    ("patch", "/api/platform/exams/e9", {"is_shared": False}),
    ("delete", "/api/platform/exams/e9", None),
    ("patch", "/api/platform/courses/c9", {"is_shared": False}),
    ("delete", "/api/platform/courses/c9", None),
    ("delete", "/api/platform/in-progress/p9", None),
]


@pytest.mark.parametrize("path", PLATFORM_GET_PATHS)
async def test_student_is_blocked_from_platform_routes(as_student: AsyncClient, path: str):
    assert (await as_student.get(path)).status_code == 403


@pytest.mark.parametrize("path", PLATFORM_GET_PATHS)
async def test_instructor_is_blocked_from_platform_routes(as_instructor: AsyncClient, path: str):
    # Instructors teach; they do not administer the deployment. These routes
    # can change any account's role, so the gate is exact equality.
    assert (await as_instructor.get(path)).status_code == 403


@pytest.mark.parametrize("method,path,payload", PLATFORM_MUTATIONS)
async def test_instructor_cannot_call_platform_mutations(
    as_instructor: AsyncClient, method: str, path: str, payload: dict | None
):
    kwargs = {"json": payload} if payload is not None else {}
    assert (await getattr(as_instructor, method)(path, **kwargs)).status_code == 403


@pytest.mark.parametrize("method,path,payload", PLATFORM_MUTATIONS)
async def test_anonymous_cannot_call_platform_mutations(
    anon: AsyncClient, method: str, path: str, payload: dict | None
):
    kwargs = {"json": payload} if payload is not None else {}
    assert (await getattr(anon, method)(path, **kwargs)).status_code == 401


@pytest.mark.parametrize(
    "path",
    ["/api/admin/dashboard", "/api/admin/overview", "/api/admin/students"],
)
async def test_admin_is_blocked_from_instructor_routes(as_admin: AsyncClient, path: str):
    # Admin is a third role, not a teacher. The class pages stay behind the
    # instructor gate; the platform console is the admin's equivalent.
    assert (await as_admin.get(path)).status_code == 403


async def test_platform_reachable_while_impersonating(student, admin, anon: AsyncClient):
    """An impersonation session keeps `/api/platform/*` open for the real admin.

    Overrides both deps the same way a real JWT would: effective identity is the
    student, while `require_admin` resolves the actor from the `act` claim.
    """
    app.dependency_overrides[get_current_user] = lambda: student
    app.dependency_overrides[require_admin] = lambda: admin
    try:
        # overview hits the DB; the gate is what we care about — anything past
        # 403 means AdminDep accepted the impersonating session.
        resp = await anon.get("/api/platform/overview")
        assert resp.status_code != 403
        assert resp.status_code != 401
    finally:
        app.dependency_overrides.clear()


async def test_start_impersonation_refuses_self(admin):
    with pytest.raises(ImpersonateSelfRefused):
        await platform_service.start_impersonation(
            admin.id, admin, db=None, already_impersonating=False
        )


async def test_start_impersonation_refuses_nested(admin, student, monkeypatch):
    async def fake_get(_user_id, _db):
        return student

    monkeypatch.setattr(platform_service, "_get_or_404", fake_get)
    with pytest.raises(AlreadyImpersonating):
        await platform_service.start_impersonation(
            student.id, admin, db=None, already_impersonating=True
        )


async def test_start_impersonation_refuses_admin_target(admin, monkeypatch):
    other_admin = type(admin)(
        id="u9",
        email="other@example.com",
        password_hash="",
        role=UserRole.ADMIN,
        display_name="Other",
        created_at=admin.created_at,
    )

    async def fake_get(_user_id, _db):
        return other_admin

    monkeypatch.setattr(platform_service, "_get_or_404", fake_get)
    with pytest.raises(ImpersonateAdminRefused):
        await platform_service.start_impersonation(
            other_admin.id, admin, db=None, already_impersonating=False
        )


async def test_end_impersonation_refuses_when_not_impersonating(admin, student):
    with pytest.raises(NotImpersonating):
        await platform_service.end_impersonation(
            admin, student, db=None, is_impersonating=False
        )


async def test_require_admin_resolves_act_claim_from_real_jwt(admin, student, monkeypatch):
    """Impersonation JWTs still open the platform gate for the real admin."""
    from starlette.requests import Request

    admin.token_version = 0
    student.token_version = 0
    token = auth_service.create_impersonation_token(admin, student)

    async def fake_get_by_id(user_id, _db):
        if user_id == admin.id:
            return admin
        if user_id == student.id:
            return student
        return None

    monkeypatch.setattr(auth_service, "get_by_id", fake_get_by_id)

    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )
    # Mimic get_current_user stashing the actor after a successful token resolve.
    identities = await auth_service.identities_from_token(token, db=None)
    assert identities is not None
    effective, actor = identities
    request.state.impersonation_actor = actor
    assert await require_admin(request, effective) is admin


async def test_instructor_gate_accepts_the_string_the_column_stores(instructor):
    # User.role is String(10). After Postgres the value is the str "instructor",
    # not the UserRole member. The fixtures construct users with the enum, so
    # they cannot catch an `is` comparison — and that is exactly what 403'd a
    # student who had just been promoted.
    instructor.role = "instructor"
    assert await require_instructor(instructor) is instructor

    instructor.role = "student"
    with pytest.raises(InstructorRequired):
        await require_instructor(instructor)


def test_every_audit_action_falls_under_a_filterable_area():
    # The audit page filters by prefix ("user." selects every account action) and
    # offers one chip per area. An action in a sixth area would be reachable only
    # under "All", so adding one has to mean adding its chip too.
    for action in AuditAction:
        area, _, verb = str(action).partition(".")
        assert verb, f"{action} is missing its <area>.<verb> shape"
        assert area in AUDIT_AREAS, f"{action} needs '{area}' in AUDIT_AREAS and a chip to match"


def test_the_platform_reset_route_goes_through_the_audited_service():
    # This route duplicates DELETE /api/admin/in-progress/{id}, and the audit
    # entry is the entire reason it exists. Reaching past its own service to
    # `reset_attempt_unscoped` would delete the same row while logging nothing,
    # leaving the two routes indistinguishable.
    source = (SRC / "platform_admin" / "router.py").read_text(encoding="utf-8")
    assert "reset_attempt_unscoped" not in source
    assert "service.reset_attempt(record_id, user, db)" in source

    # The service reads the row before deleting it, so the entry can name the
    # student and exam instead of an id that no longer resolves to anything.
    service_source = (SRC / "platform_admin" / "service.py").read_text(encoding="utf-8")
    assert "AuditAction.ATTEMPT_RESET" in service_source


async def test_admin_is_not_staff():
    # STAFF_ROLES is who teaches: shared content, enrolment codes, a class page.
    # An admin does none of those, so putting them in here would mint them a
    # code and list them on every instructor picker.
    assert UserRole.ADMIN not in STAFF_ROLES
    assert UserRole.INSTRUCTOR in STAFF_ROLES
    assert UserRole.STUDENT not in STAFF_ROLES


async def test_student_cannot_create_exam_from_bank(as_student: AsyncClient):
    resp = await as_student.post(
        "/api/exams/from-bank",
        json={
            "title": "x",
            "bank_id": "b" * 12,
            "shares": [{"section_id": "s" * 12, "percent": 50}],
            "questions_per_attempt": 10,
            "pass_grade": 72,
        },
    )
    assert resp.status_code == 403


async def test_anonymous_profile_mutations_are_rejected(anon: AsyncClient):
    # These write the caller's own row, so an unauthenticated one has nothing to
    # write — and the avatar delete unlinks a file.
    assert (await anon.patch("/api/auth/me", json={"display_name": "x"})).status_code == 401
    assert (await anon.delete("/api/auth/me/avatar")).status_code == 401


# ── Input bounds: 422, never 500 ───────────────────────────────────

ONE_QUESTION = {"topic": "t", "type": "MCQ", "question": "q", "answer": "a"}


@pytest.mark.parametrize(
    "url,payload",
    [
        ("/api/exams", {"title": "x" * 300, "questions": []}),
        ("/api/exams", {"title": "ok", "questions": [], "time_limit_minutes": 9_999_999_999}),
        ("/api/exams", {"title": "ok", "questions": [ONE_QUESTION] * (MAX_QUESTIONS_PER_EXAM + 1)}),
        # 0 is not a pass mark and >100 is unreachable: either would be an exam
        # that every attempt passes, or one that none can.
        ("/api/exams", {"title": "ok", "questions": [], "pass_grade": 0}),
        ("/api/exams", {"title": "ok", "questions": [], "pass_grade": 101}),
        ("/api/courses", {"name": "x" * 300}),
        (
            "/api/exams/abc/submit",
            {"exam_id": "abc", "answers": [], "time_spent_seconds": 9_999_999_999},
        ),
        (
            "/api/in-progress",
            {
                "exam_id": "abc",
                # A non-numeric answer key would otherwise wedge the admin
                # dashboard's int() conversion for every instructor.
                "answers": {"notanumber": 1},
                "flagged": [],
                "question_order": [],
                "remaining_seconds": 10,
            },
        ),
    ],
)
async def test_out_of_bounds_input_is_422(as_student: AsyncClient, url: str, payload: dict):
    assert (await as_student.post(url, json=payload)).status_code == 422


async def test_blank_title_is_rejected_on_create_too(as_student: AsyncClient):
    # Create and rename share one title rule now; before, a blank title was a
    # 400 on rename and silently accepted on create.
    resp = await as_student.post("/api/exams", json={"title": "   ", "questions": []})
    assert resp.status_code == EmptyTitle.STATUS_CODE == 400
    assert resp.json()["detail"] == EmptyTitle.DETAIL


async def test_null_answer_is_rejected(as_student: AsyncClient):
    # Question.answer is NOT NULL, so an explicit null used to reach the driver
    # and surface as a 500 — on submit, that costs a student their attempt.
    null_answer = {**ONE_QUESTION, "answer": None}
    resp = await as_student.post("/api/exams", json={"title": "ok", "questions": [null_answer]})
    assert resp.status_code == 422

    resp = await as_student.patch("/api/exams/abc/questions/1", json={"answer": None})
    assert resp.status_code == 422


async def test_legacy_question_number_is_ignored(as_student: AsyncClient):
    # Pre-drop JSON uploads still carry `"number"`. Extra fields must not 422 —
    # the column is gone, and identity is Question.id assigned on insert.
    body = {**ONE_QUESTION, "number": 1}
    resp = await as_student.post("/api/exams", json={"title": "ok", "questions": [body]})
    assert resp.status_code != 422


@pytest.mark.parametrize("pass_grade", [0, 101, -5])
async def test_out_of_range_pass_grade_update_is_422(as_student: AsyncClient, pass_grade: int):
    resp = await as_student.patch("/api/exams/abc/pass-grade", json={"pass_grade": pass_grade})
    assert resp.status_code == 422


@pytest.mark.parametrize("pass_grade", [1, 72, 100])
async def test_in_range_pass_grade_update_passes_validation(as_student: AsyncClient, pass_grade: int):
    # Reaches the dead DB and 500s, which is proof that validation let it through.
    resp = await as_student.patch("/api/exams/abc/pass-grade", json={"pass_grade": pass_grade})
    assert resp.status_code != 422


async def test_pass_grade_defaults_rather_than_being_required(as_student: AsyncClient):
    # Existing API callers predate the field, so omitting it must not 422 — the
    # upload form is what makes it a required input.
    resp = await as_student.post("/api/exams", json={"title": "ok", "questions": []})
    assert resp.status_code != 422


async def test_history_carries_the_threshold_it_was_graded_against():
    # Editing an exam's pass grade must not relabel attempts that are already
    # graded, which is only possible because History has its own copy.
    assert "pass_grade" in HistorySummaryOut.model_fields


# ── Registration roles ─────────────────────────────────────────────
#
# `register` does two SELECTs then an add and a commit, so a stub session covers
# it without Postgres — the same reason the rest of this file needs no database.


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Returns the queued values, in order, from successive execute() calls."""

    def __init__(self, results):
        self._results = list(results)
        self.added = []

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._results.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass


def _register_payload(**overrides) -> RegisterIn:
    return RegisterIn(**{"email": "new@example.com", "password": "password1", **overrides})


def test_registration_defaults_to_student():
    # A payload with no role must never mint an instructor.
    assert _register_payload(invite_code="x").role is UserRole.STUDENT


@pytest.mark.parametrize("role", ["admin", "Instructor", "superuser", ""])
async def test_unknown_registration_role_is_422(anon: AsyncClient, role: str):
    body = {"email": "a@b.co", "password": "password1", "invite_code": "x", "role": role}
    assert (await anon.post("/api/auth/register", json=body)).status_code == 422


def test_admin_is_a_real_role_but_not_a_registrable_one():
    # "admin" is 422 above because of RegisterIn's validator, NOT because the role
    # does not exist — it does, and the distinction is the whole vulnerability.
    # `register`'s student branch stores whatever role it is handed, so with admin
    # left registrable, anyone holding an instructor's enrolment code could sign
    # themselves up as one.
    assert UserRole.ADMIN in UserRole
    assert UserRole.ADMIN not in REGISTRABLE_ROLES
    assert set(REGISTRABLE_ROLES) == {UserRole.STUDENT, UserRole.INSTRUCTOR}


async def test_register_service_refuses_an_admin_role_on_its_own(instructor):
    # Defence in depth: bypass the schema entirely and call the service with an
    # admin role and a valid enrolment code. It must refuse before any insert,
    # because this is the escalation path rather than a validation slip.
    payload = RegisterIn(email="x@example.com", password="password1", invite_code=instructor.invite_code)
    # model_construct skips validation, standing in for a future caller that
    # reaches the service without going through RegisterIn.
    escalated = payload.model_copy(update={"role": UserRole.ADMIN})
    db = _FakeSession([instructor, None])

    with pytest.raises(RegistrationClosed):
        await auth_service.register(escalated, db)
    assert db.added == []


async def test_wrong_instructor_code_cannot_mint_an_instructor(anon: AsyncClient):
    # The only gate on instructor sign-up is AUTH_INSTRUCTOR_INVITE_CODE, so a
    # wrong value must fail before any database work.
    body = {
        "email": "a@b.co",
        "password": "password1",
        "invite_code": "definitely-not-the-code",
        "role": "instructor",
    }
    resp = await anon.post("/api/auth/register", json=body)
    assert resp.status_code == InvalidInviteCode.STATUS_CODE == 403
    assert resp.json()["detail"] == InvalidInviteCode.DETAIL


async def test_student_registration_links_the_instructor_and_mints_no_code(instructor):
    # The invite-code lookup finds the instructor; the email lookup finds nobody.
    db = _FakeSession([instructor, None])
    user = await auth_service.register(_register_payload(invite_code=instructor.invite_code), db)

    assert user.role is UserRole.STUDENT
    assert user.instructor_id == instructor.id
    # A student holding an invite code could enrol other students under themselves.
    assert user.invite_code is None
    # NULL display_name is what sends the new account through onboarding.
    assert user.display_name is None


async def test_unknown_student_invite_code_is_rejected():
    # No instructor owns that code, and there is no shared student code any more,
    # so there is no way to create a student who belongs to nobody.
    db = _FakeSession([None])
    with pytest.raises(InvalidInviteCode):
        await auth_service.register(_register_payload(invite_code="nobodys-code"), db)


async def test_instructor_registration_mints_a_personal_code():
    db = _FakeSession([None])
    payload = _register_payload(invite_code=auth_settings.instructor_invite_code, role=UserRole.INSTRUCTOR)
    user = await auth_service.register(payload, db)

    assert user.role is UserRole.INSTRUCTOR
    # Without a code of their own an instructor cannot enrol anybody.
    assert user.invite_code
    assert user.instructor_id is None


def test_svg_is_not_an_allowed_image_type():
    # SVGs are served from the app's own origin, so a script inside one is
    # stored XSS.
    assert ".svg" not in ALLOWED_IMAGE_EXTENSIONS


def test_not_owned_is_indistinguishable_from_not_found():
    # Both must be 404: a 403 would confirm that an id exists to someone who
    # cannot see it, which is an enumeration oracle.
    assert ExamNotFound.STATUS_CODE == QuestionNotFound.STATUS_CODE == 404


@pytest.mark.parametrize("percent", [0, 101, -1])
def test_section_share_percent_is_bounded(percent: int):
    with pytest.raises(ValidationError):
        ExamFromBank(
            title="x",
            bank_id="b" * 12,
            shares=[{"section_id": "s" * 12, "percent": percent}],
            questions_per_attempt=10,
            pass_grade=72,
        )


@pytest.mark.parametrize("total", [0, -1])
def test_from_bank_attempt_size_is_bounded(total: int):
    with pytest.raises(ValidationError):
        ExamFromBank(
            title="x",
            bank_id="b" * 12,
            shares=[{"section_id": "s" * 12, "percent": 50}],
            questions_per_attempt=total,
            pass_grade=72,
        )


def test_allocate_section_draws_hits_total():
    assert allocate_section_draws(10, [100, 100], [50, 50]) == [5, 5]
    assert allocate_section_draws(10, [100, 100], [70, 30]) == [7, 3]
    # Short section: leftover seats spill so the attempt still has 10 questions.
    assert allocate_section_draws(10, [5, 100], [70, 30]) == [5, 5]
    # Legacy: percent of each section's own size (Python 3 round, 2.5 → 2).
    assert allocate_section_draws(None, [5, 10], [50, 100]) == [2, 10]
    assert allocate_section_draws(1, [10, 10], [50, 50]) == [1, 0]


async def test_instructor_bank_title_too_long_is_422(as_instructor: AsyncClient):
    resp = await as_instructor.post("/api/question-banks", json={"title": "x" * 300})
    assert resp.status_code == 422


def test_bank_backed_attempts_draw_server_side():
    # A client-supplied question_order on a bank exam would let a student pick
    # the paper. The first insert must sample, and later saves must not rewrite it.
    source = (SRC / "attempts" / "service.py").read_text(encoding="utf-8")
    assert "draw_attempt_order" in source
    assert "if payload.mode is AttemptMode.PRACTICE and not exam.bank_id:" in source
    assert "option_order" in source


@pytest.mark.parametrize(
    "url,payload",
    [
        (
            "/api/in-progress",
            {
                "exam_id": "abc",
                "mode": "cheat",
                "answers": {},
                "flagged": [],
                "question_order": [],
                "remaining_seconds": 10,
            },
        ),
        ("/api/exams/abc/submit", {"exam_id": "abc", "answers": [], "time_spent_seconds": 1, "mode": "cheat"}),
    ],
)
async def test_unknown_attempt_mode_is_rejected(as_student: AsyncClient, url: str, payload: dict):
    # `mode` is the third component of the attempt's unique key, so a free-form
    # value let one user mint unlimited attempt rows carrying megabytes of JSONB.
    assert (await as_student.post(url, json=payload)).status_code == 422


def test_graded_attempts_cannot_self_mark_or_pick_their_own_questions():
    # Both fields stay in the schema (wire contract) but submit ignores them for
    # a graded run: self-marking was a free 100%, and question_ids let a
    # student be scored over only the questions they got right.
    source = (SRC / "attempts" / "service.py").read_text(encoding="utf-8")
    assert "graded = mode is AttemptMode.EXAM" in source
    assert "fuzzy_fib=not graded" in source


def test_graded_fib_is_not_fuzzy():
    # With self-marking gone, the deliberately lenient substring match would
    # otherwise decide real marks: "tach" would score "tachycardia".
    q = SimpleNamespace(type="FIB", options=None, answer="tachycardia")
    assert grade_question(q, "tach", fuzzy_fib=True)
    assert not grade_question(q, "tach", fuzzy_fib=False)
    assert grade_question(q, "tachycardia", fuzzy_fib=False)


def test_ids_are_wide_enough_and_unique():
    ids = {new_id() for _ in range(5000)}
    assert len(ids) == 5000
    assert all(len(i) == ID_LENGTH for i in ids)
    # 8 chars was 32 bits, which collides at ~1.2% by 10k rows.
    assert ID_LENGTH >= 12


# ── Route ordering ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "router,fixed,parameterized",
    [
        (progress_router, "/api/in-progress/by-exam/{exam_id}", "/api/in-progress/{record_id}"),
        (history_router, "/api/history/topic-stats", "/api/history/{record_id}"),
        (exams_router, "/api/exams/from-bank", "/api/exams/{exam_id}"),
        (exams_router, "/api/exams/instructors/search", "/api/exams/{exam_id}"),
    ],
)
def test_fixed_paths_precede_parameterized_siblings(router, fixed: str, parameterized: str):
    # Otherwise "topic-stats" is captured as a record id and the route returns a
    # silent 404 that surfaces as an empty chart.
    paths = [r.path for r in router.routes]
    assert paths.index(fixed) < paths.index(parameterized)


# ── Failure shape (the configured database really is unreachable) ──


async def test_healthz_is_503_when_the_database_is_down(anon: AsyncClient):
    resp = await anon.get("/healthz")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unhealthy"


async def test_unhandled_500_is_json_with_detail(as_student: AsyncClient):
    # Reaches the dead database, so this exercises the global handler.
    resp = await as_student.get("/api/exams")
    assert resp.status_code == 500
    assert resp.headers["content-type"].split(";")[0] == "application/json"
    # The frontend reads err.error.detail on every failed request.
    assert "detail" in resp.json()
