from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text
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
        Index(None, "bank_id"),
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
    # The passing score as a percentage, 1-100. No server_default: the create
    # service always supplies it (the schema defaults it), so a missing value
    # should be a loud error rather than a silent 72.
    pass_grade = Column(Integer, nullable=False)
    # When false, take-exam keeps insertion order (Question.id) instead of shuffling.
    shuffle = Column(Boolean, nullable=False, default=True)
    # How many questions a student sits per attempt. Null = every question.
    # Unused on bank-backed exams — the per-section shares are the mix.
    questions_per_attempt = Column(Integer, nullable=True)
    # When set, questions live on the bank; each attempt draws from it.
    bank_id = Column(String(ID_LENGTH), ForeignKey("question_bank.id", ondelete="RESTRICT"), nullable=True)
    created_at = Column(DateTime, nullable=False)

    course = relationship("Course", back_populates="exams")
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan", order_by="Question.id")
    section_shares = relationship(
        "ExamSectionShare",
        back_populates="exam",
        cascade="all, delete-orphan",
    )


class ExamSectionShare(Base):
    """What percent of a bank section to draw on each attempt of this exam."""

    __tablename__ = "exam_section_share"
    __table_args__ = (Index(None, "section_id"),)

    exam_id = Column(String(ID_LENGTH), ForeignKey("exam.id", ondelete="CASCADE"), primary_key=True)
    section_id = Column(String(ID_LENGTH), ForeignKey("bank_section.id", ondelete="CASCADE"), primary_key=True)
    percent = Column(Integer, nullable=False)

    exam = relationship("Exam", back_populates="section_shares")


class Question(Base):
    """Owned transitively through Exam or BankSection — there is no owner column here.

    Any route that reaches a question by bare id must join Exam or BankSection→
    QuestionBank and check owner_id: `question.id` is a serial integer and
    trivially enumerable, unlike the random ids used everywhere else.
    """

    __tablename__ = "question"
    __table_args__ = (
        Index(None, "exam_id"),
        Index(None, "section_id"),
        CheckConstraint("(exam_id IS NULL) != (section_id IS NULL)", name="exam_xor_section"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(String(ID_LENGTH), ForeignKey("exam.id", ondelete="CASCADE"), nullable=True)
    section_id = Column(String(ID_LENGTH), ForeignKey("bank_section.id", ondelete="CASCADE"), nullable=True)
    topic = Column(Text, nullable=False, default="")
    type = Column(String(30), nullable=False, default="MCQ")
    question = Column(Text, nullable=False)
    options = Column(JSONB, nullable=True)
    answer = Column(JSONB, nullable=False)
    rationale = Column(Text, nullable=False, default="")
    image = Column(Text, nullable=True)
    sections = Column(JSONB, nullable=True)

    exam = relationship("Exam", back_populates="questions")
    bank_section = relationship("BankSection", back_populates="questions")
