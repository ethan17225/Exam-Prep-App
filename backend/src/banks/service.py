from datetime import datetime

from sqlalchemy import bindparam, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.auth.models import User
from src.banks.exceptions import BankNotFound, EmptyBankTitle, EmptySectionName, SectionNotFound
from src.banks.models import BankCollaborator, BankSection, QuestionBank
from src.banks.schemas import BankCreate, BankUpdate, SectionCreate, SectionUpdate
from src.courses import service as courses_service
from src.identifiers import new_id


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise EmptyBankTitle()
    return cleaned


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise EmptySectionName()
    return cleaned


def is_bank_collaborator(user_id: str) -> ColumnElement[bool]:
    """Correlated EXISTS against the outer QuestionBank row."""
    return exists(
        select(1).where(
            BankCollaborator.bank_id == QuestionBank.id,
            BankCollaborator.user_id == user_id,
        )
    )


def bank_writable(user: User) -> ColumnElement[bool]:
    return or_(QuestionBank.owner_id == user.id, is_bank_collaborator(user.id))


def bank_accessible(user: User) -> ColumnElement[bool]:
    """Banks are never student-visible; access is owner or collaborator only."""
    return bank_writable(user)


async def get_owned_or_404(bank_id: str, user: User, db: AsyncSession) -> QuestionBank:
    """Owner-only. Delete and similar stay here so collaborators cannot remove a bank."""
    stmt = (
        select(QuestionBank)
        .options(joinedload(QuestionBank.course), selectinload(QuestionBank.sections))
        .where(QuestionBank.id == bank_id, QuestionBank.owner_id == user.id)
    )
    bank = (await db.execute(stmt)).scalars().unique().one_or_none()
    if not bank:
        raise BankNotFound()
    return bank


async def get_writable_or_404(bank_id: str, user: User, db: AsyncSession) -> QuestionBank:
    stmt = (
        select(QuestionBank)
        .options(joinedload(QuestionBank.course), selectinload(QuestionBank.sections))
        .where(QuestionBank.id == bank_id, bank_writable(user))
    )
    bank = (await db.execute(stmt)).scalars().unique().one_or_none()
    if not bank:
        raise BankNotFound()
    return bank


async def get_owned_section_or_404(bank_id: str, section_id: str, user: User, db: AsyncSession) -> BankSection:
    """Owner-only section gate (delete section)."""
    stmt = (
        select(BankSection)
        .join(QuestionBank, BankSection.bank_id == QuestionBank.id)
        .where(
            BankSection.id == section_id,
            BankSection.bank_id == bank_id,
            QuestionBank.owner_id == user.id,
        )
    )
    section = (await db.execute(stmt)).scalar_one_or_none()
    if not section:
        raise SectionNotFound()
    return section


async def get_writable_section_or_404(bank_id: str, section_id: str, user: User, db: AsyncSession) -> BankSection:
    stmt = (
        select(BankSection)
        .join(QuestionBank, BankSection.bank_id == QuestionBank.id)
        .where(
            BankSection.id == section_id,
            BankSection.bank_id == bank_id,
            bank_writable(user),
        )
    )
    section = (await db.execute(stmt)).scalar_one_or_none()
    if not section:
        raise SectionNotFound()
    return section


def _summary(bank: QuestionBank, section_count: int, question_count: int, user: User, is_collaborator: bool) -> dict:
    return {
        "id": bank.id,
        "title": bank.title,
        "course_id": bank.course_id,
        "course_name": bank.course.name if bank.course else None,
        "section_count": section_count,
        "question_count": question_count,
        "created_at": bank.created_at,
        "is_owner": bank.owner_id == user.id,
        "is_collaborator": is_collaborator,
    }


async def list_mine(user: User, db: AsyncSession) -> list[dict]:
    banks = list(
        (
            await db.execute(
                select(QuestionBank)
                .options(joinedload(QuestionBank.course))
                .where(bank_accessible(user))
                .order_by(QuestionBank.created_at.desc())
            )
        )
        .scalars()
        .unique()
        .all()
    )
    if not banks:
        return []

    bank_ids = [b.id for b in banks]
    collab_ids = set(
        (
            await db.execute(
                select(BankCollaborator.bank_id).where(
                    BankCollaborator.user_id == user.id,
                    BankCollaborator.bank_id.in_(bank_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    section_counts = dict(
        (
            await db.execute(
                select(BankSection.bank_id, func.count(BankSection.id))
                .where(BankSection.bank_id.in_(bank_ids))
                .group_by(BankSection.bank_id)
            )
        ).all()
    )
    question_rows = (
        await db.execute(
            text(
                """
                SELECT s.bank_id, COUNT(q.id) AS n
                FROM bank_section s
                JOIN question q ON q.section_id = s.id
                WHERE s.bank_id IN :ids
                GROUP BY s.bank_id
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": bank_ids},
        )
    ).all()
    question_counts = {row.bank_id: row.n for row in question_rows}
    return [
        _summary(b, section_counts.get(b.id, 0), question_counts.get(b.id, 0), user, b.id in collab_ids) for b in banks
    ]


async def create(payload: BankCreate, user: User, db: AsyncSession) -> QuestionBank:
    title = _clean_title(payload.title)
    if payload.course_id:
        await courses_service.get_visible_or_404(payload.course_id, user, db)
    bank = QuestionBank(
        id=new_id(),
        owner_id=user.id,
        title=title,
        course_id=payload.course_id,
        created_at=datetime.now(),
    )
    db.add(bank)
    await db.commit()
    return bank


async def detail(bank_id: str, user: User, db: AsyncSession) -> dict:
    stmt = (
        select(QuestionBank)
        .options(
            joinedload(QuestionBank.course),
            selectinload(QuestionBank.sections).selectinload(BankSection.questions),
        )
        .where(QuestionBank.id == bank_id, bank_accessible(user))
    )
    bank = (await db.execute(stmt)).scalars().unique().one_or_none()
    if not bank:
        raise BankNotFound()
    is_collaborator = bank.owner_id != user.id and await db.scalar(
        select(BankCollaborator.bank_id).where(
            BankCollaborator.bank_id == bank.id,
            BankCollaborator.user_id == user.id,
        )
    )
    return {
        "id": bank.id,
        "title": bank.title,
        "course_id": bank.course_id,
        "course_name": bank.course.name if bank.course else None,
        "created_at": bank.created_at,
        "is_owner": bank.owner_id == user.id,
        "is_collaborator": bool(is_collaborator),
        "sections": [
            {
                "id": section.id,
                "name": section.name,
                "position": section.position,
                "question_count": len(section.questions),
                "questions": section.questions,
            }
            for section in bank.sections
        ],
    }


async def update(bank_id: str, payload: BankUpdate, user: User, db: AsyncSession) -> QuestionBank:
    bank = await get_writable_or_404(bank_id, user, db)
    if "title" in payload.model_fields_set and payload.title is not None:
        bank.title = _clean_title(payload.title)
    if "course_id" in payload.model_fields_set:
        if payload.course_id:
            await courses_service.get_visible_or_404(payload.course_id, user, db)
        bank.course_id = payload.course_id
    await db.commit()
    return bank


async def delete_bank(bank_id: str, user: User, db: AsyncSession) -> None:
    bank = await get_owned_or_404(bank_id, user, db)
    await db.delete(bank)
    await db.commit()


async def add_section(bank_id: str, payload: SectionCreate, user: User, db: AsyncSession) -> BankSection:
    await get_writable_or_404(bank_id, user, db)
    name = _clean_name(payload.name)
    max_pos = await db.scalar(select(func.max(BankSection.position)).where(BankSection.bank_id == bank_id)) or 0
    section = BankSection(
        id=new_id(),
        bank_id=bank_id,
        name=name,
        position=int(max_pos) + 1,
    )
    db.add(section)
    await db.commit()
    return section


async def rename_section(
    bank_id: str, section_id: str, payload: SectionUpdate, user: User, db: AsyncSession
) -> BankSection:
    section = await get_writable_section_or_404(bank_id, section_id, user, db)
    section.name = _clean_name(payload.name)
    await db.commit()
    return section


async def delete_section(bank_id: str, section_id: str, user: User, db: AsyncSession) -> None:
    section = await get_writable_section_or_404(bank_id, section_id, user, db)
    await db.delete(section)
    await db.commit()


async def grant_collaborator(bank_id: str, user_id: str, invited_by: str, db: AsyncSession) -> None:
    """Upsert bank access. Does not commit — the exam share path owns the transaction."""
    existing = await db.scalar(
        select(BankCollaborator.bank_id).where(
            BankCollaborator.bank_id == bank_id,
            BankCollaborator.user_id == user_id,
        )
    )
    if existing:
        return
    db.add(
        BankCollaborator(
            bank_id=bank_id,
            user_id=user_id,
            invited_by=invited_by,
            created_at=datetime.now(),
        )
    )


async def revoke_collaborator(bank_id: str, user_id: str, db: AsyncSession) -> None:
    """Remove bank access. Does not commit — caller owns the transaction."""
    row = (
        await db.execute(
            select(BankCollaborator).where(
                BankCollaborator.bank_id == bank_id,
                BankCollaborator.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        await db.delete(row)
