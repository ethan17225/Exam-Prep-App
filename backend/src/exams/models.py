from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.database import Base
from src.identifiers import ID_LENGTH


class Exam(Base):
    __tablename__ = "exam"
    __table_args__ = (
        Index(None, "owner_id"),
        # Postgres does not auto-index foreign keys.
        Index(None, "course_id"),
    )

    id = Column(String(ID_LENGTH), primary_key=True)
    owner_id = Column(String(ID_LENGTH), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    # Set server-side from the creator's role; never accepted from the client.
    is_shared = Column(Boolean, nullable=False)
    # Whether the answer key may leave the server for a non-owner. False makes an
    # exam assessment-only: no practice mode, no flashcards, no answers in the
    # take-exam payload. This is the single gate on answer-key disclosure.
    allow_practice = Column(Boolean, nullable=False)
    course_id = Column(String(ID_LENGTH), ForeignKey("course.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    time_limit_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)

    course = relationship("Course", back_populates="exams")
    questions = relationship(
        "Question", back_populates="exam", cascade="all, delete-orphan", order_by="Question.number"
    )


class Question(Base):
    """Owned transitively through Exam — there is no owner column here.

    Any route that reaches a question by bare id must join Exam and check
    Exam.owner_id: `question.id` is a serial integer and trivially enumerable,
    unlike the random ids used everywhere else.
    """

    __tablename__ = "question"
    __table_args__ = (Index(None, "exam_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(String(ID_LENGTH), ForeignKey("exam.id", ondelete="CASCADE"), nullable=False)
    number = Column(Integer, nullable=False)
    topic = Column(Text, nullable=False, default="")
    type = Column(String(30), nullable=False, default="MCQ")
    question = Column(Text, nullable=False)
    options = Column(JSONB, nullable=True)
    answer = Column(JSONB, nullable=False)
    rationale = Column(Text, nullable=False, default="")
    image = Column(Text, nullable=True)
    sections = Column(JSONB, nullable=True)

    exam = relationship("Exam", back_populates="questions")
