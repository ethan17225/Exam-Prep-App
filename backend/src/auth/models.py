from sqlalchemy import Column, DateTime, Integer, String

from src.auth.constants import UserRole
from src.database import Base
from src.identifiers import ID_LENGTH


class User(Base):
    # "user" is a Postgres reserved word. SQLAlchemy quotes identifiers
    # automatically so the ORM is unaffected; only hand-written SQL would need
    # to spell it "user".
    __tablename__ = "user"

    id = Column(String(ID_LENGTH), primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(60), nullable=False)
    role = Column(String(10), nullable=False, default=UserRole.STUDENT)
    # Bumped on password change and on sign-out-everywhere. Tokens carry the
    # value they were minted with, so bumping it revokes every outstanding one —
    # otherwise a stolen 12-hour JWT outlives logout with no way to kill it.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False)
