from sqlalchemy import Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB

from src.database import Base
from src.identifiers import ID_LENGTH


class AdminAuditLog(Base):
    """Append-only record of every mutating admin action.

    The audit log is the only account of who changed a role, reset a password or
    deleted someone's work, so it is written to but never updated, and nothing in
    the API deletes from it.

    Like every other model module this imports only `src.database`: the FK target
    below is a string resolved from the shared registry.
    """

    __tablename__ = "admin_audit_log"
    __table_args__ = (Index(None, "created_at"),)

    id = Column(String(ID_LENGTH), primary_key=True)
    # SET NULL rather than CASCADE: deleting an admin must not erase the record of
    # what they did. `actor_email` is what keeps the row readable afterwards.
    actor_id = Column(String(ID_LENGTH), ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    actor_email = Column(String(255), nullable=False)
    action = Column(String(40), nullable=False)
    target_type = Column(String(20), nullable=False)
    # No FK: the whole point of several of these rows is that the target is gone.
    target_id = Column(String(ID_LENGTH), nullable=True)
    # Frozen at write time — the exam title or email as it was — so the log still
    # reads correctly after a rename, a transfer or a delete.
    target_label = Column(String(255), nullable=False, default="")
    # Callable default, not a literal: a shared mutable default bleeds one row's
    # payload into the next.
    detail = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, nullable=False)
