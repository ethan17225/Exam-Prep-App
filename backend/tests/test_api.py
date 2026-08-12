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

from src.attempts.router import history_router, progress_router
from src.attempts.schemas import HistorySummaryOut
from src.auth import service as auth_service
from src.auth.config import auth_settings
from src.auth.constants import UserRole
from src.auth.exceptions import InvalidInviteCode
from src.auth.schemas import RegisterIn
from src.constants import MAX_QUESTIONS_PER_EXAM
from src.exams.exceptions import EmptyTitle, ExamNotFound, QuestionNotFound
from src.grading.service import grade_question
from src.identifiers import ID_LENGTH, new_id
from src.storage import ALLOWED_IMAGE_EXTENSIONS

SRC = Path(__file__).resolve().parent.parent / "src"

ANONYMOUS_GET_PATHS = [
    "/api/exams",
    "/api/courses",
    "/api/history",
    "/api/history/topic-stats",
    "/api/in-progress",
    "/api/admin/dashboard",
    "/api/admin/overview",
    "/api/admin/students",
    "/api/admin/students/u1",
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


async def test_garbage_token_is_rejected(anon: AsyncClient):
    resp = await anon.get("/api/exams", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "path",
    ["/api/admin/dashboard", "/api/admin/overview", "/api/admin/students", "/api/admin/students/u9"],
)
async def test_student_is_blocked_from_instructor_routes(as_student: AsyncClient, path: str):
    assert (await as_student.get(path)).status_code == 403


async def test_anonymous_profile_mutations_are_rejected(anon: AsyncClient):
    # These write the caller's own row, so an unauthenticated one has nothing to
    # write — and the avatar delete unlinks a file.
    assert (await anon.patch("/api/auth/me", json={"display_name": "x"})).status_code == 401
    assert (await anon.delete("/api/auth/me/avatar")).status_code == 401


# ── Input bounds: 422, never 500 ───────────────────────────────────

ONE_QUESTION = {"number": 1, "topic": "t", "type": "MCQ", "question": "q", "answer": "a"}


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


async def test_question_number_may_be_omitted(as_student: AsyncClient):
    # The route documents "omit `number` to append at the end", so omitting it
    # must not be a validation error. (It reaches the dead DB and 500s, which is
    # proof enough that validation let it through.)
    body = {k: v for k, v in ONE_QUESTION.items() if k != "number"}
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
    # a graded run: self-marking was a free 100%, and question_numbers let a
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
