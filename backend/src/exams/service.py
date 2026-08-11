from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.auth.constants import UserRole
from src.auth.models import User
from src.authz import visible
from src.courses import service as courses_service
from src.courses.models import Course
from src.exams.exceptions import ExamNotFound, ExamNotOwned, QuestionNotFound
from src.exams.models import Exam, Question
from src.exams.schemas import ExamCreate, QuestionIn
from src.grading.service import TypeCountRow, question_type_counts


async def get_visible_exam_or_404(exam_id: str, user: User, db: AsyncSession, with_questions: bool = False) -> Exam:
    """Read access. Deliberately a plain function, not a FastAPI dependency:
    dependencies resolve before the request body is validated, so making this a
    dependency would turn a malformed-payload 422 into a 403/404."""
    stmt = select(Exam).where(Exam.id == exam_id, visible(Exam, user))
    if with_questions:
        # Otherwise `exam.questions` lazy-loads, which raises under async.
        stmt = stmt.options(selectinload(Exam.questions))
    exam = (await db.execute(stmt)).scalar_one_or_none()
    if not exam:
        raise ExamNotFound()
    return exam


async def get_owned_exam_or_404(exam_id: str, user: User, db: AsyncSession) -> Exam:
    """Write access. Being able to see a shared exam never implies being able to
    change it, so this is separate from the read predicate."""
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise ExamNotFound()
    if exam.owner_id != user.id:
        raise ExamNotOwned()
    return exam


async def get_owned_question_or_404(question_id: int, user: User, db: AsyncSession) -> Question:
    """`question.id` is a serial integer and trivially enumerable, and these
    routes carry no exam_id, so ownership is resolved by joining through Exam."""
    stmt = (
        select(Question)
        .join(Exam, Question.exam_id == Exam.id)
        .where(Question.id == question_id, Exam.owner_id == user.id)
    )
    question = (await db.execute(stmt)).scalar_one_or_none()
    if not question:
        raise QuestionNotFound()
    return question


async def questions_by_exam_ids(exam_ids, db: AsyncSession):
    """Rows needed to grade, batched for many exams at once. Only the three
    columns grading reads — the full rows carry JSONB deserialized for nothing."""
    stmt = select(Question.exam_id, Question.number, Question.type, Question.answer, Question.options).where(
        Question.exam_id.in_(exam_ids)
    )
    return (await db.execute(stmt)).all()


async def _type_count_rows(exam_ids, db: AsyncSession):
    stmt = select(Question.exam_id, Question.type, Question.options).where(Question.exam_id.in_(exam_ids))
    # Column-tuple select: .scalars() here would silently discard every column
    # but the first.
    return (await db.execute(stmt)).all()


async def exam_summary(exam: Exam, db: AsyncSession) -> dict:
    rows = await _type_count_rows([exam.id], db)
    counts = [TypeCountRow(qtype, options) for _, qtype, options in rows]
    mcq, sata, fib, other = question_type_counts(counts)

    # Always query the course rather than reading exam.course: callers reach here
    # after db.refresh(), which expires relationships unconditionally.
    course = None
    if exam.course_id:
        course = (await db.execute(select(Course).where(Course.id == exam.course_id))).scalar_one_or_none()

    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": course.name if course else None,
        "time_limit_minutes": exam.time_limit_minutes,
        "total_questions": len(counts),
        "mcq_count": mcq,
        "sata_count": sata,
        "fib_count": fib,
        "other_count": other,
        "created_at": exam.created_at.isoformat(),
    }


async def list_summaries(user: User, course_id: str | None, db: AsyncSession) -> list[dict]:
    stmt = select(Exam).options(joinedload(Exam.course)).where(visible(Exam, user))
    if course_id:
        stmt = stmt.where(Exam.course_id == course_id)
    stmt = stmt.order_by(Exam.created_at)
    exams = list((await db.execute(stmt)).scalars().unique().all())

    counts: dict[str, list[TypeCountRow]] = {e.id: [] for e in exams}
    if counts:
        for exam_id, qtype, options in await _type_count_rows(list(counts.keys()), db):
            counts[exam_id].append(TypeCountRow(qtype, options))

    out = []
    for exam in exams:
        rows = counts.get(exam.id, [])
        mcq, sata, fib, other = question_type_counts(rows)
        out.append(
            {
                "id": exam.id,
                "title": exam.title,
                "course_id": exam.course_id,
                "course_name": exam.course.name if exam.course else None,
                "time_limit_minutes": exam.time_limit_minutes,
                "total_questions": len(rows),
                "mcq_count": mcq,
                "sata_count": sata,
                "fib_count": fib,
                "other_count": other,
                "created_at": exam.created_at.isoformat(),
            }
        )
    return out


async def create(payload: ExamCreate, user: User, db: AsyncSession) -> dict:
    if payload.course_id:
        # Validates that the course is visible to the caller; raises CourseNotFound.
        await courses_service.get_visible_or_404(payload.course_id, user, db)

    exam_id = str(uuid4())[:8]
    db.add(
        Exam(
            id=exam_id,
            owner_id=user.id,
            is_shared=user.role == UserRole.INSTRUCTOR,
            title=payload.title,
            course_id=payload.course_id,
            time_limit_minutes=payload.time_limit_minutes,
            created_at=datetime.now(),
        )
    )
    for q in payload.questions:
        db.add(
            Question(
                exam_id=exam_id,
                number=q.number,
                topic=q.topic,
                type=q.type,
                question=q.question,
                sections=q.sections,
                options=q.options,
                answer=q.answer,
                rationale=q.rationale,
                image=q.image,
            )
        )
    await db.commit()
    return {"exam_id": exam_id, "total_questions": len(payload.questions)}


async def detail(exam_id: str, user: User, include_answers: bool, db: AsyncSession) -> dict:
    stmt = (
        select(Exam)
        # Both eager loads are required: the loop reads exam.questions and the
        # return reads exam.course.
        .options(joinedload(Exam.course), selectinload(Exam.questions))
        .where(Exam.id == exam_id, visible(Exam, user))
    )
    exam = (await db.execute(stmt)).scalars().unique().one_or_none()
    if not exam:
        raise ExamNotFound()

    questions = []
    for q in exam.questions:
        qdict = {
            "id": q.id,
            "number": q.number,
            "topic": q.topic,
            "type": q.type,
            "question": q.question,
            "sections": q.sections,
            "options": q.options,
            "image": q.image,
        }
        if include_answers:
            qdict["answer"] = q.answer
            qdict["rationale"] = q.rationale or ""
        questions.append(qdict)

    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": exam.course.name if exam.course else None,
        "time_limit_minutes": exam.time_limit_minutes,
        "questions": questions,
    }


def question_to_dict(q: Question) -> dict:
    return {
        "id": q.id,
        "number": q.number,
        "topic": q.topic,
        "type": q.type,
        "question": q.question,
        "sections": q.sections,
        "options": q.options,
        "answer": q.answer,
        "rationale": q.rationale or "",
        "image": q.image,
    }


async def next_question_number(exam_id: str, db: AsyncSession) -> int:
    current = await db.scalar(select(func.max(Question.number)).where(Question.exam_id == exam_id))
    return (current or 0) + 1


async def add_question(exam_id: str, payload: QuestionIn, db: AsyncSession) -> Question:
    number = payload.number
    if not number or number <= 0:
        number = await next_question_number(exam_id, db)
    q = Question(
        exam_id=exam_id,
        number=number,
        topic=payload.topic,
        type=payload.type,
        question=payload.question,
        sections=payload.sections,
        options=payload.options,
        answer=payload.answer,
        rationale=payload.rationale,
        image=payload.image,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


async def get_question_in_exam_or_404(exam_id: str, question_id: int, db: AsyncSession) -> Question:
    stmt = select(Question).where(Question.id == question_id, Question.exam_id == exam_id)
    q = (await db.execute(stmt)).scalar_one_or_none()
    if not q:
        raise QuestionNotFound()
    return q


async def image_urls_for_exam(exam_id: str, db: AsyncSession) -> list[str]:
    stmt = select(Question.image).where(Question.exam_id == exam_id)
    # Single column, so .scalars() is correct here.
    return [url for url in (await db.execute(stmt)).scalars().all() if url]
