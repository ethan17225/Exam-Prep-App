from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base


class Exam(Base):
    __tablename__ = "exams"

    id = Column(String(8), primary_key=True)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)

    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan", order_by="Question.number")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(String(8), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    number = Column(Integer, nullable=False)
    topic = Column(Text, nullable=False, default="")
    type = Column(String(30), nullable=False, default="MCQ")
    question = Column(Text, nullable=False)
    options = Column(JSONB, nullable=True)
    answer = Column(JSONB, nullable=False)
    rationale = Column(Text, nullable=False, default="")

    exam = relationship("Exam", back_populates="questions")


class InProgressExam(Base):
    __tablename__ = "in_progress_exams"

    id = Column(String(8), primary_key=True)
    exam_id = Column(String(8), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    exam_title = Column(String(255), nullable=False)
    mode = Column(String(10), nullable=False, default="exam")
    answers = Column(JSONB, nullable=False, default={})
    flagged = Column(JSONB, nullable=False, default=[])
    question_order = Column(JSONB, nullable=False, default=[])
    remaining_seconds = Column(Integer, nullable=False)
    current_page = Column(Integer, nullable=False, default=0)
    total_questions = Column(Integer, nullable=False)
    answered_count = Column(Integer, nullable=False, default=0)
    saved_at = Column(DateTime, nullable=False)

    exam = relationship("Exam")


class History(Base):
    __tablename__ = "history"

    id = Column(String(8), primary_key=True)
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
