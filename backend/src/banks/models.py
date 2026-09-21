from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from src.database import Base
from src.identifiers import ID_LENGTH


class QuestionBank(Base):
    """Instructor-owned pool. Never listed to students; exams created from it are."""

    __tablename__ = "question_bank"
    __table_args__ = (Index(None, "owner_id"),)

    id = Column(String(ID_LENGTH), primary_key=True)
    owner_id = Column(String(ID_LENGTH), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    course_id = Column(String(ID_LENGTH), ForeignKey("course.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)

    course = relationship("Course")
    sections = relationship(
        "BankSection",
        back_populates="bank",
        cascade="all, delete-orphan",
        order_by="BankSection.position",
    )


class BankSection(Base):
    """A named grouping inside a bank. Distinct from Question.sections (patient-data tabs)."""

    __tablename__ = "bank_section"
    __table_args__ = (Index(None, "bank_id"),)

    id = Column(String(ID_LENGTH), primary_key=True)
    bank_id = Column(String(ID_LENGTH), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    position = Column(Integer, nullable=False)

    bank = relationship("QuestionBank", back_populates="sections")
    questions = relationship(
        "Question",
        back_populates="bank_section",
        cascade="all, delete-orphan",
        order_by="Question.id",
    )
