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
from src.constants import MAX_QUESTIONS_PER_EXAM
from src.exams.constants import ALLOWED_IMAGE_EXTENSIONS
from src.exams.exceptions import EmptyTitle, ExamNotFound, QuestionNotFound
from src.grading.service import grade_question
from src.identifiers import ID_LENGTH, new_id

SRC = Path(__file__).resolve().parent.parent / "src"

ANONYMOUS_GET_PATHS = [
    "/api/exams",
    "/api/courses",
    "/api/history",
    "/api/history/topic-stats",
    "/api/in-progress",
    "/api/admin/dashboard",
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


async def test_student_is_blocked_from_the_dashboard(as_student: AsyncClient):
    assert (await as_student.get("/api/admin/dashboard")).status_code == 403


# ── Input bounds: 422, never 500 ───────────────────────────────────

ONE_QUESTION = {"number": 1, "topic": "t", "type": "MCQ", "question": "q", "answer": "a"}


@pytest.mark.parametrize(
    "url,payload",
    [
        ("/api/exams", {"title": "x" * 300, "questions": []}),
        ("/api/exams", {"title": "ok", "questions": [], "time_limit_minutes": 9_999_999_999}),
        ("/api/exams", {"title": "ok", "questions": [ONE_QUESTION] * (MAX_QUESTIONS_PER_EXAM + 1)}),
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
