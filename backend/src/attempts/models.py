from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.database import Base


class InProgressExam(Base):
    __tablename__ = "in_progress_exam"
    __table_args__ = (
        # Autosave fires on a 500ms debounce and two tabs will collide, so the
        # upsert in service.save_progress depends on this constraint existing.
        UniqueConstraint("user_id", "exam_id", "mode"),
        Index("in_progress_exam_user_id_saved_at_idx", "user_id", "saved_at"),
    )

    id = Column(String(8), primary_key=True)
    user_id = Column(String(8), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    exam_id = Column(String(8), ForeignKey("exam.id", ondelete="CASCADE"), nullable=False)
    exam_title = Column(String(255), nullable=False)
    mode = Column(String(10), nullable=False, default="exam")
    # Callables, not literals: a shared mutable default can bleed one row's
    # answers into the next.
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
        Index("history_user_id_taken_at_idx", "user_id", "taken_at"),
        Index(None, "exam_id"),
    )

    id = Column(String(8), primary_key=True)
    user_id = Column(String(8), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    # exam_id deliberately has NO ForeignKey: history must survive exam deletion.
    # Consequently, never join(Exam) on a history query — an inner join silently
    # drops every row whose exam is gone.
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
