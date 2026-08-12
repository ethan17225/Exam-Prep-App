"""Shared fixtures.

These tests deliberately need **no database**. `get_db` constructs its session
lazily, so a request rejected before any query (a 401, or a 422 from request
validation) never opens a connection — which is what lets the whole auth and
validation surface be covered without Postgres.
"""

import os
from datetime import datetime

# Must be set before src.config is imported: settings are read at import time.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@unreachable-host:5432/unused")
os.environ.setdefault("AUTH_SECRET", "unit-test-secret-at-least-32-characters-long")
os.environ.setdefault("AUTH_INSTRUCTOR_INVITE_CODE", "unit-test-instructor-invite")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx2 import ASGITransport, AsyncClient  # noqa: E402

from src.auth.constants import UserRole  # noqa: E402
from src.auth.dependencies import get_current_user  # noqa: E402
from src.auth.models import User  # noqa: E402
from src.main import app  # noqa: E402


def _client() -> AsyncClient:
    # raise_app_exceptions=False is the equivalent of TestClient's
    # raise_server_exceptions=False, and is NOT the default: without it the
    # unhandled-500 checks raise the underlying error instead of asserting on it.
    return AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


@pytest.fixture
def student() -> User:
    return User(
        id="u1",
        email="student@example.com",
        password_hash="",
        role=UserRole.STUDENT,
        display_name="Student One",
        instructor_id="u2",
        created_at=datetime.now(),
    )


@pytest.fixture
def instructor() -> User:
    return User(
        id="u2",
        email="instructor@example.com",
        password_hash="",
        role=UserRole.INSTRUCTOR,
        display_name="Instructor Two",
        invite_code="instructorcode",
        created_at=datetime.now(),
    )


@pytest_asyncio.fixture
async def anon() -> AsyncClient:
    """Unauthenticated client."""
    async with _client() as client:
        yield client


@pytest_asyncio.fixture
async def as_student(student: User) -> AsyncClient:
    """Client authenticated as a student, via dependency_overrides.

    A plain sync lambda overriding an async dependency is fully supported by
    FastAPI — do not "fix" it to an async def.
    """
    app.dependency_overrides[get_current_user] = lambda: student
    async with _client() as client:
        yield client
    app.dependency_overrides.clear()
