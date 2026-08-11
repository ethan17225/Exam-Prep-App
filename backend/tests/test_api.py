"""HTTP-level checks that need no database and no running server.

Two things must never regress silently: every route requiring a session, and bad
input producing a 422 rather than a 500 (a 500 on submit costs a student their
completed attempt). Ownership behaviour needs real rows — that lives in
test_e2e.py.
"""

import pytest
from httpx2 import AsyncClient

from src.attempts.router import history_router, progress_router
from src.constants import MAX_QUESTIONS_PER_EXAM
from src.exams.constants import ALLOWED_IMAGE_EXTENSIONS

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


def test_svg_is_not_an_allowed_image_type():
    # SVGs are served from the app's own origin, so a script inside one is
    # stored XSS.
    assert ".svg" not in ALLOWED_IMAGE_EXTENSIONS


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
