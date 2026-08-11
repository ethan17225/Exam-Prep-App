from fastapi import APIRouter, status

from src.auth.dependencies import CurrentUserDep
from src.courses import service
from src.courses.exceptions import CourseNameEmpty, CourseNameTaken
from src.courses.schemas import CourseCreate, CourseOut
from src.database import SessionDep

router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.get(
    "",
    response_model=list[CourseOut],
    summary="List courses",
    description="Courses shared by an instructor, plus any the caller created.",
)
async def list_courses(user: CurrentUserDep, db: SessionDep):
    return await service.list_visible(user, db)


@router.post(
    "",
    response_model=CourseOut,
    summary="Create a course",
    description=(
        "Creates a course owned by the caller. Instructor-created courses are "
        "visible to everyone; student-created ones are private."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": CourseNameEmpty.DETAIL},
        status.HTTP_409_CONFLICT: {"description": CourseNameTaken.DETAIL},
    },
)
async def create_course(payload: CourseCreate, user: CurrentUserDep, db: SessionDep):
    return await service.create(payload, user, db)
