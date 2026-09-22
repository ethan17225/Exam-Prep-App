"""Auth primitives — the pieces where a bug is a security hole rather than a
visible failure: password hashing, token round-tripping, expiry, tampering, and
the visibility predicate."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from src.auth import service
from src.auth.config import auth_settings
from src.auth.constants import JWT_ALGORITHM, UserRole
from src.auth.models import User
from src.authz import visible
from src.courses.models import Course

# SecretStr keeps the value out of crash logs; tests need the raw key to forge
# and verify tokens.
SECRET = auth_settings.secret.get_secret_value()


def _decodes(token: str) -> bool:
    try:
        jwt.decode(token, SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except jwt.InvalidTokenError:
        return False


# ── Passwords ──────────────────────────────────────────────────────


async def test_password_round_trip():
    hashed = await service.hash_password("correct horse battery staple")
    assert await service.verify_password("correct horse battery staple", hashed)
    assert not await service.verify_password("wrong password", hashed)


async def test_hash_is_salted():
    a = await service.hash_password("same password")
    b = await service.hash_password("same password")
    assert a != b


async def test_hash_fits_the_column():
    # models.User.password_hash is String(60).
    assert len(await service.hash_password("x" * 40)) <= 60


async def test_72_byte_truncation_is_consistent():
    # bcrypt ignores everything past 72 bytes; verification must truncate the
    # same way the hashing did, or long passwords fail to validate.
    hashed = await service.hash_password("x" * 72 + "AAAA")
    assert await service.verify_password("x" * 72 + "BBBB", hashed)


# ── Tokens ─────────────────────────────────────────────────────────


@pytest.fixture
def instructor_user() -> User:
    return User(
        id="abc12345",
        email="i@example.com",
        password_hash="",
        role=UserRole.INSTRUCTOR,
        created_at=datetime.now(),
    )


def test_token_carries_subject_and_role(instructor_user: User):
    payload = jwt.decode(service.create_token(instructor_user), SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["sub"] == "abc12345"
    assert payload["role"] == UserRole.INSTRUCTOR


def test_token_ttl_is_12_hours(instructor_user: User):
    payload = jwt.decode(service.create_token(instructor_user), SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["exp"] - payload["iat"] == int(timedelta(hours=12).total_seconds())


@pytest.fixture
def admin_user() -> User:
    return User(
        id="admin0001",
        email="admin@example.com",
        password_hash="",
        role=UserRole.ADMIN,
        token_version=3,
        created_at=datetime.now(),
    )


@pytest.fixture
def student_user() -> User:
    return User(
        id="stu000001",
        email="student@example.com",
        password_hash="",
        role=UserRole.STUDENT,
        token_version=1,
        created_at=datetime.now(),
    )


def test_impersonation_token_carries_target_and_actor(admin_user: User, student_user: User):
    payload = jwt.decode(
        service.create_impersonation_token(admin_user, student_user),
        SECRET,
        algorithms=[JWT_ALGORITHM],
    )
    assert payload["sub"] == student_user.id
    assert payload["role"] == UserRole.STUDENT
    assert payload["ver"] == student_user.token_version
    assert payload["act"] == admin_user.id
    assert payload["act_ver"] == admin_user.token_version
    assert "act" not in jwt.decode(
        service.create_token(student_user), SECRET, algorithms=[JWT_ALGORITHM]
    )


async def test_resolve_actor_rejects_stale_act_ver(admin_user: User, student_user: User, monkeypatch):
    token = service.create_impersonation_token(admin_user, student_user)
    payload = service.decode_token(token)
    assert payload is not None

    stale = User(
        id=admin_user.id,
        email=admin_user.email,
        password_hash="",
        role=UserRole.ADMIN,
        token_version=admin_user.token_version + 1,
        created_at=datetime.now(),
    )

    async def fake_get_by_id(user_id, _db):
        if user_id == admin_user.id:
            return stale
        if user_id == student_user.id:
            return student_user
        return None

    monkeypatch.setattr(service, "get_by_id", fake_get_by_id)
    assert await service.resolve_actor_from_payload(payload, db=None) is None
    assert await service.user_from_token(token, db=None) is None


async def test_resolve_actor_rejects_non_admin_act(admin_user: User, student_user: User, monkeypatch):
    token = service.create_impersonation_token(admin_user, student_user)
    payload = service.decode_token(token)
    assert payload is not None

    demoted = User(
        id=admin_user.id,
        email=admin_user.email,
        password_hash="",
        role=UserRole.INSTRUCTOR,
        token_version=admin_user.token_version,
        created_at=datetime.now(),
    )

    async def fake_get_by_id(user_id, _db):
        if user_id == admin_user.id:
            return demoted
        if user_id == student_user.id:
            return student_user
        return None

    monkeypatch.setattr(service, "get_by_id", fake_get_by_id)
    assert await service.resolve_actor_from_payload(payload, db=None) is None
    assert await service.user_from_token(token, db=None) is None


async def test_user_from_token_accepts_valid_impersonation(
    admin_user: User, student_user: User, monkeypatch
):
    token = service.create_impersonation_token(admin_user, student_user)

    async def fake_get_by_id(user_id, _db):
        if user_id == admin_user.id:
            return admin_user
        if user_id == student_user.id:
            return student_user
        return None

    monkeypatch.setattr(service, "get_by_id", fake_get_by_id)
    user = await service.user_from_token(token, db=None)
    assert user is student_user
    actor = await service.resolve_actor_from_payload(service.decode_token(token), db=None)
    assert actor is admin_user


def test_token_signed_with_another_key_is_rejected():
    forged = jwt.encode({"sub": "abc12345", "role": "instructor"}, "not-the-secret", algorithm="HS256")
    assert not _decodes(forged)
    assert service.decode_token(forged) is None


def test_expired_token_is_rejected():
    now = datetime.now(UTC)
    expired = jwt.encode(
        {"sub": "abc12345", "iat": now - timedelta(hours=24), "exp": now - timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )
    assert not _decodes(expired)
    assert service.decode_token(expired) is None


def test_alg_none_token_is_rejected():
    assert not _decodes(jwt.encode({"sub": "x"}, key="", algorithm="none"))


# ── Visibility predicate ───────────────────────────────────────────


def _sql(user: User) -> str:
    return str(visible(Course, user).compile(compile_kwargs={"literal_binds": True}))


def test_visible_matches_shared_or_own(student: User):
    sql = _sql(student)
    assert "is_shared IS true" in sql
    assert f"owner_id = '{student.id}'" in sql
    # An OR, not an AND — otherwise nothing shared would ever be visible.
    assert " OR " in sql and " AND " not in sql


def test_instructors_get_no_visibility_bypass(student: User, instructor: User):
    # Role must not appear in the read predicate at all: visibility is frozen at
    # creation time, so promoting a student must never publish their drafts.
    instructor.id = student.id
    assert _sql(student) == _sql(instructor)
