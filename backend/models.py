from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, Index, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base

# Ownership model:
#   content  (courses, exams) -> owner_id + is_shared. Readable when
#            `is_shared OR owner_id == me`; writable only by the owner.
#            `is_shared` is set by the server from the creator's role and is
#            never accepted from the client.
#   questions -> owned transitively through Exam. Every route reaching a
#            question by bare id must join Exam and check Exam.owner_id.
#   attempts (in_progress_exams, history) -> user_id, always filtered strictly.


class User(Base):
    __tablename__ = "users"

    id = Column(String(8), primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(60), nullable=False)
    role = Column(String(10), nullable=False, default="student")
    created_at = Column(DateTime, nullable=False)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_courses_owner_id_name"),
        Index("ix_courses_owner_id", "owner_id"),
    )

    id = Column(String(8), primary_key=True)
    owner_id = Column(String(8), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_shared = Column(Boolean, nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)

    exams = relationship("Exam", back_populates="course")
    owner = relationship("User")


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        Index("ix_exams_owner_id", "owner_id"),
        Index("ix_exams_course_id", "course_id"),
    )

    id = Column(String(8), primary_key=True)
    owner_id = Column(String(8), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_shared = Column(Boolean, nullable=False)
    course_id = Column(String(8), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    time_limit_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)

    course = relationship("Course", back_populates="exams")
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan", order_by="Question.number")
    owner = relationship("User")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_exam_id", "exam_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(String(8), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
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


class InProgressExam(Base):
    __tablename__ = "in_progress_exams"
    __table_args__ = (
        UniqueConstraint("user_id", "exam_id", "mode", name="uq_in_progress_user_exam_mode"),
        Index("ix_in_progress_exams_user_id_saved_at", "user_id", "saved_at"),
    )

    id = Column(String(8), primary_key=True)
    user_id = Column(String(8), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exam_id = Column(String(8), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    exam_title = Column(String(255), nullable=False)
    mode = Column(String(10), nullable=False, default="exam")
    # Callables, not literals: a shared mutable default can bleed one row's answers into the next.
    answers = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    flagged = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    question_order = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    remaining_seconds = Column(Integer, nullable=False)
    current_page = Column(Integer, nullable=False, default=0)
    total_questions = Column(Integer, nullable=False)
    answered_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    saved_at = Column(DateTime, nullable=False)

    exam = relationship("Exam")
    user = relationship("User")


class History(Base):
    __tablename__ = "history"
    __table_args__ = (
        Index("ix_history_user_id_taken_at", "user_id", "taken_at"),
        Index("ix_history_exam_id", "exam_id"),
    )

    id = Column(String(8), primary_key=True)
    user_id = Column(String(8), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # exam_id deliberately has NO ForeignKey: history must survive exam deletion.
    # Never join(Exam) on a history query — an inner join silently drops those rows.
    exam_id = Column(String(8), nullable=False)
    exam_title = Column(String(255), nullable=False)
    score = Column(Float, nullable=False)
    correct = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    time_spent_seconds = Column(Integer, nullable=False)
    results = Column(JSONB, nullable=False)
    mode = Column(String(10), nullable=True, default="exam", server_default="exam")
    taken_at = Column(DateTime, nullable=False)

    user = relationship("User")
