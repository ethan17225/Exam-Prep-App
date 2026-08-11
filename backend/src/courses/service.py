from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.constants import UserRole
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
        is_shared=user.role == UserRole.INSTRUCTOR,
        name=name,
        created_at=datetime.now(),
    )
    db.add(course)
    await db.commit()
    return course
