from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.constants import STAFF_ROLES
from src.auth.models import User
from src.authz import visible
from src.courses.exceptions import CourseNameEmpty, CourseNameTaken, CourseNotFound
from src.courses.models import Course
from src.courses.schemas import CourseCreate
from src.identifiers import new_id


async def list_visible(user: User, db: AsyncSession) -> list[Course]:
    stmt = select(Course).where(visible(Course, user)).order_by(Course.name)
    return list((await db.execute(stmt)).scalars().all())


async def get_visible_or_404(course_id: str, user: User, db: AsyncSession) -> Course:
    stmt = select(Course).where(Course.id == course_id, visible(Course, user))
    course = (await db.execute(stmt)).scalar_one_or_none()
    if not course:
        raise CourseNotFound()
    return course


async def create(payload: CourseCreate, user: User, db: AsyncSession) -> Course:
    name = payload.name.strip()
    if not name:
        raise CourseNameEmpty()

    # Names are unique per owner now, so only my own courses can collide.
    clash = (
        await db.execute(select(Course).where(Course.owner_id == user.id, Course.name == name))
    ).scalar_one_or_none()
    if clash:
        raise CourseNameTaken()

    course = Course(
        id=new_id(),
        owner_id=user.id,
        is_shared=user.role in STAFF_ROLES,
        name=name,
        created_at=datetime.now(),
    )
    db.add(course)
    await db.commit()
    return course


# ── Administration ────────────────────────────────────────────────
#
# Cross-owner reads and writes, `_unscoped` for the same reason as their
# counterparts in `exams.service`: nothing here applies `visible()` or an
# ownership filter, and their only callers sit behind the admin gate.


def _admin_filters(query: str | None, owner_id: str | None) -> list:
    filters = []
    if owner_id:
        filters.append(Course.owner_id == owner_id)
    if query and (needle := query.strip().lower()):
        filters.append(func.lower(Course.name).like(f"%{needle}%"))
    return filters


async def list_all_unscoped(
    db: AsyncSession,
    query: str | None = None,
    owner_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Course]:
    stmt = (
        select(Course)
        .where(*_admin_filters(query, owner_id))
        .order_by(Course.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_all_unscoped(db: AsyncSession, query: str | None = None, owner_id: str | None = None) -> int:
    return await db.scalar(select(func.count(Course.id)).where(*_admin_filters(query, owner_id))) or 0


async def count_all(db: AsyncSession) -> int:
    return await db.scalar(select(func.count(Course.id))) or 0


async def get_or_404_unscoped(course_id: str, db: AsyncSession) -> Course:
    course = (await db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
    if not course:
        raise CourseNotFound()
    return course


async def set_shared_unscoped(course: Course, is_shared: bool, db: AsyncSession) -> Course:
    course.is_shared = is_shared
    await db.commit()
    return course


async def transfer_owner_unscoped(course: Course, owner_id: str, db: AsyncSession) -> Course:
    """Course names are unique per owner, so a transfer can collide with a course
    the recipient already has. Checked up front: reaching the constraint instead
    surfaces as an IntegrityError, i.e. a 500."""
    clash = (
        await db.execute(select(Course).where(Course.owner_id == owner_id, Course.name == course.name))
    ).scalar_one_or_none()
    if clash and clash.id != course.id:
        raise CourseNameTaken()

    course.owner_id = owner_id
    await db.commit()
    return course


async def delete_unscoped(course: Course, db: AsyncSession) -> None:
    """Exams keep existing — `exam.course_id` is ON DELETE SET NULL, so deleting a
    course unfiles its exams rather than destroying them."""
    await db.delete(course)
    await db.commit()
