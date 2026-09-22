"""Instructor exam collaboration — auth, validation, and service rules.

Ownership behaviour against real rows still needs a live DB (e2e). These tests
cover the peer-share surface that must stay correct without Postgres: route
guards, invite validation, and the owner-vs-collaborator predicates.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx2 import AsyncClient
from sqlalchemy import select

from src.auth.constants import UserRole
from src.auth.models import User
from src.banks.models import BankCollaborator, QuestionBank
from src.exams.exceptions import (
    AlreadyCollaborator,
    CannotShareWithSelf,
    CollaboratorNotFound,
    InstructorNotFound,
)
from src.exams.models import Exam, ExamCollaborator
from src.exams.schemas import ExamCollaboratorInvite, ExamDetailOut, ExamSummaryOut
from src.exams.service import (
    add_collaborator,
    exam_readable,
    exam_writable,
    list_collaborators,
    remove_collaborator,
)
from src.main import app


def _instructor(uid: str = "ownr", email: str = "owner@example.com") -> User:
    return User(
        id=uid,
        email=email,
        password_hash="",
        role=UserRole.INSTRUCTOR,
        display_name="Owner",
        invite_code="code",
        created_at=datetime.now(),
    )


def _exam(*, owner_id: str = "ownr", bank_id: str | None = None) -> Exam:
    return Exam(
        id="examexamexam",
        owner_id=owner_id,
        is_shared=True,
        allow_practice=False,
        title="Shared Exam",
        pass_grade=72,
        shuffle=True,
        bank_id=bank_id,
        created_at=datetime.now(),
    )


# ── HTTP surface ───────────────────────────────────────────────────


async def test_anonymous_collaborator_routes_are_rejected(anon: AsyncClient):
    assert (await anon.get("/api/exams/abc/collaborators")).status_code == 401
    assert (
        await anon.post("/api/exams/abc/collaborators", json={"email": "x@y.com"})
    ).status_code == 401
    assert (await anon.delete("/api/exams/abc/collaborators/u1")).status_code == 401


async def test_student_cannot_manage_collaborators(as_student: AsyncClient):
    assert (await as_student.get("/api/exams/abc/collaborators")).status_code == 403
    assert (
        await as_student.post("/api/exams/abc/collaborators", json={"email": "x@y.com"})
    ).status_code == 403
    assert (await as_student.delete("/api/exams/abc/collaborators/u1")).status_code == 403


async def test_collaborator_invite_requires_email(as_instructor: AsyncClient):
    # Reaches validation before the dead database — empty body is a 422.
    resp = await as_instructor.post("/api/exams/abc/collaborators", json={})
    assert resp.status_code == 422


def test_collaborator_routes_are_registered():
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/exams/{exam_id}/collaborators" in paths
    assert "/api/exams/{exam_id}/collaborators/{user_id}" in paths


def test_summary_and_detail_schemas_include_collaborator_flag():
    assert "is_collaborator" in ExamSummaryOut.model_fields
    assert "is_collaborator" in ExamDetailOut.model_fields
    invite = ExamCollaboratorInvite(email="peer@example.com")
    assert invite.email == "peer@example.com"


# ── Predicates ─────────────────────────────────────────────────────


def test_exam_readable_includes_owner_shared_and_collaborator():
    owner = _instructor("ownr")
    readable = exam_readable(owner)
    # Compiles against Exam so a typo in the EXISTS would fail collection.
    stmt = select(Exam).where(readable)
    sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "exam_collaborator" in sql.lower()
    assert "is_shared" in sql.lower() or "is_shared" in sql


def test_exam_writable_is_owner_or_collaborator_not_shared():
    owner = _instructor("ownr")
    writable = exam_writable(owner)
    compiled = select(Exam.id).where(writable).compile(compile_kwargs={"literal_binds": False})
    where_sql = str(compiled).lower()
    assert "exam_collaborator" in where_sql
    # Writable must not treat classroom publish (`is_shared`) as edit access.
    assert "is_shared" not in where_sql


def test_bank_collaborator_table_is_modeled():
    assert BankCollaborator.__tablename__ == "bank_collaborator"
    assert QuestionBank.__tablename__ == "question_bank"


# ── Service rules (mocked session) ─────────────────────────────────


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalars.return_value.unique.return_value.one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_add_collaborator_rejects_self():
    owner = _instructor()
    exam = _exam(owner_id=owner.id)
    db = AsyncMock()
    # get_owned_exam_or_404
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), _scalar_result(owner)])
    with pytest.raises(CannotShareWithSelf):
        await add_collaborator(exam.id, owner.email, owner, db)


@pytest.mark.asyncio
async def test_add_collaborator_rejects_non_instructor():
    owner = _instructor()
    exam = _exam(owner_id=owner.id)
    student = User(
        id="stud",
        email="student@example.com",
        password_hash="",
        role=UserRole.STUDENT,
        display_name="Student",
        created_at=datetime.now(),
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), _scalar_result(student)])
    with pytest.raises(InstructorNotFound):
        await add_collaborator(exam.id, student.email, owner, db)


@pytest.mark.asyncio
async def test_add_collaborator_rejects_missing_email():
    owner = _instructor()
    exam = _exam(owner_id=owner.id)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), _scalar_result(None)])
    with pytest.raises(InstructorNotFound):
        await add_collaborator(exam.id, "missing@example.com", owner, db)


@pytest.mark.asyncio
async def test_add_collaborator_rejects_duplicate(monkeypatch):
    owner = _instructor()
    peer = _instructor("peer", "peer@example.com")
    exam = _exam(owner_id=owner.id)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), _scalar_result(peer)])

    async def already(_exam_id, _user_id, _db):
        return True

    monkeypatch.setattr("src.exams.service._is_collaborator", already)
    with pytest.raises(AlreadyCollaborator):
        await add_collaborator(exam.id, peer.email, owner, db)


@pytest.mark.asyncio
async def test_add_collaborator_grants_bank_access(monkeypatch):
    owner = _instructor()
    peer = _instructor("peer", "peer@example.com")
    exam = _exam(owner_id=owner.id, bank_id="bankbankbank")
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), _scalar_result(peer)])
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def not_yet(_exam_id, _user_id, _db):
        return False

    granted: list[tuple] = []

    async def grant(bank_id, user_id, invited_by, _db):
        granted.append((bank_id, user_id, invited_by))

    monkeypatch.setattr("src.exams.service._is_collaborator", not_yet)
    monkeypatch.setattr("src.exams.service.banks_service.grant_collaborator", grant)

    out = await add_collaborator(exam.id, peer.email, owner, db)
    assert out["user_id"] == peer.id
    assert out["email"] == peer.email
    assert granted == [("bankbankbank", peer.id, owner.id)]
    db.add.assert_called_once()
    assert isinstance(db.add.call_args.args[0], ExamCollaborator)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_collaborator_revokes_bank_when_unused(monkeypatch):
    owner = _instructor()
    exam = _exam(owner_id=owner.id, bank_id="bankbankbank")
    collab = ExamCollaborator(
        exam_id=exam.id,
        user_id="peer",
        invited_by=owner.id,
        created_at=datetime.now(),
    )
    db = AsyncMock()
    # owned exam, then collaborator row, then "still has access?" scalar
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), _scalar_result(collab)])
    db.scalar = AsyncMock(return_value=None)
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    revoked: list[tuple] = []

    async def revoke(bank_id, user_id, _db):
        revoked.append((bank_id, user_id))

    monkeypatch.setattr("src.exams.service.banks_service.revoke_collaborator", revoke)

    await remove_collaborator(exam.id, "peer", owner, db)
    assert revoked == [("bankbankbank", "peer")]
    db.delete.assert_awaited_once_with(collab)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_collaborator_keeps_bank_when_another_exam_shares(monkeypatch):
    owner = _instructor()
    exam = _exam(owner_id=owner.id, bank_id="bankbankbank")
    collab = ExamCollaborator(
        exam_id=exam.id,
        user_id="peer",
        invited_by=owner.id,
        created_at=datetime.now(),
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), _scalar_result(collab)])
    db.scalar = AsyncMock(return_value="otherexamexid")  # still collaborator elsewhere
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    async def revoke(*_args, **_kwargs):
        raise AssertionError("bank access must remain while another shared exam uses it")

    monkeypatch.setattr("src.exams.service.banks_service.revoke_collaborator", revoke)

    await remove_collaborator(exam.id, "peer", owner, db)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_missing_collaborator_is_404():
    owner = _instructor()
    exam = _exam(owner_id=owner.id)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), _scalar_result(None)])
    with pytest.raises(CollaboratorNotFound):
        await remove_collaborator(exam.id, "peer", owner, db)


@pytest.mark.asyncio
async def test_list_collaborators_is_owner_only():
    owner = _instructor()
    exam = _exam(owner_id=owner.id)
    peer = _instructor("peer", "peer@example.com")
    collab = ExamCollaborator(
        exam_id=exam.id,
        user_id=peer.id,
        invited_by=owner.id,
        created_at=datetime.now(),
    )
    db = AsyncMock()
    list_result = MagicMock()
    list_result.all.return_value = [(collab, peer)]
    db.execute = AsyncMock(side_effect=[_scalar_result(exam), list_result])

    rows = await list_collaborators(exam.id, owner, db)
    assert rows == [
        {"user_id": peer.id, "email": peer.email, "created_at": collab.created_at},
    ]
