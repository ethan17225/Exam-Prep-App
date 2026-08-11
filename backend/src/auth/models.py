from sqlalchemy import Column, DateTime, String

from src.auth.constants import UserRole
from src.database import Base


class User(Base):
    # "user" is a Postgres reserved word. SQLAlchemy quotes identifiers
    # automatically so the ORM is unaffected; only hand-written SQL would need
    # to spell it "user".
    __tablename__ = "user"

    id = Column(String(8), primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(60), nullable=False)
    role = Column(String(10), nullable=False, default=UserRole.STUDENT)
    created_at = Column(DateTime, nullable=False)
