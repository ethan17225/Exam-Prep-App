from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from src.attempts.constants import AttemptMode
from src.database import Base
from src.identifiers import ID_LENGTH

# A CHECK rather than a native Postgres ENUM: adding a value later needs only a
# drop-and-recreate in one revision, where ALTER TYPE cannot run in a transaction
# and autogenerate does not model it.
_MODE_IN = "mode IN ('{}')".format("', '".join(m.value for m in AttemptMode))


class InProgressExam(Base):
    __tablename__ = "in_progress_exam"
    __table_args__ = (
        # Autosave fires on a 500ms debounce and two tabs will collide, so the
        # upsert in service.save_progress depends on this constraint existing.
        UniqueConstraint("user_id", "exam_id", "mode"),
        Index("in_progress_exam_user_id_saved_at_idx", "user_id", "saved_at"),
        # Backstop for the enum in the schemas: mode is part of the unique key,
        # so an unconstrained value means unlimited rows per user per exam.
        CheckConstraint(_MODE_IN, name="mode_valid"),
    )

    id = Column(String(ID_LENGTH), primary_key=True)
    user_id = Column(String(ID_LENGTH), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    exam_id = Column(String(ID_LENGTH), ForeignKey("exam.id", ondelete="CASCADE"), nullable=False)
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
    # NOT NULL: this is the authoritative clock for a graded attempt. It is set
    # once on insert and deliberately never rewritten by the upsert, so a student
    # cannot restart the timer by autosaving.
    started_at = Column(DateTime, nullable=False)
    saved_at = Column(DateTime, nullable=False)

    # Only `user` is declared: the dashboard eager-loads it for the student's
    # email. Every other access goes through exam_id, so an Exam relationship
    # would be a lazy-load trap that nothing needs.
    user = relationship("User")


class History(Base):
    __tablename__ = "history"
    __table_args__ = (
        Index("history_user_id_taken_at_idx", "user_id", "taken_at"),
        Index(None, "exam_id"),
        CheckConstraint(_MODE_IN, name="mode_valid"),
    )

    id = Column(String(ID_LENGTH), primary_key=True)
    user_id = Column(String(ID_LENGTH), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    # exam_id deliberately has NO ForeignKey: history must survive exam deletion.
    # Consequently, never join(Exam) on a history query — an inner join silently
    # drops every row whose exam is gone.
    exam_id = Column(String(ID_LENGTH), nullable=False)
    exam_title = Column(String(255), nullable=False)
    score = Column(Float, nullable=False)
    correct = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    # The threshold this attempt was graded against, copied from the exam. History
    # is denormalized and outlives the exam, so without its own copy an instructor
    # editing the pass grade would retroactively relabel past attempts.
    pass_grade = Column(Integer, nullable=False)
    time_spent_seconds = Column(Integer, nullable=False)
    results = Column(JSONB, nullable=False)
    # NOT NULL: a nullable mode forced a defensive `record.mode or "exam"` in one
    # serializer and not the others.
    mode = Column(String(10), nullable=False, default=AttemptMode.EXAM, server_default="exam")
    # Whether the submission arrived after the time limit plus grace. No
    # server_default: History is constructed in exactly one place, so a missing
    # value should be a loud error rather than a silent False.
    over_time = Column(Boolean, nullable=False, default=False)
    taken_at = Column(DateTime, nullable=False)

    user = relationship("User")
