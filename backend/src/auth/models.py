from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from src.auth.constants import UserRole
from src.database import Base
from src.identifiers import ID_LENGTH

# The preferred name collected during onboarding.
DISPLAY_NAME_MAX = 80


class User(Base):
    # "user" is a Postgres reserved word. SQLAlchemy quotes identifiers
    # automatically so the ORM is unaffected; only hand-written SQL would need
    # to spell it "user".
    __tablename__ = "user"
    __table_args__ = (
        # Postgres does not auto-index foreign keys, and every instructor
        # analytics query filters on this column.
        Index(None, "instructor_id"),
    )

    id = Column(String(ID_LENGTH), primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(60), nullable=False)
    role = Column(String(10), nullable=False, default=UserRole.STUDENT)
    # Bumped on password change and on sign-out-everywhere. Tokens carry the
    # value they were minted with, so bumping it revokes every outstanding one —
    # otherwise a stolen 12-hour JWT outlives logout with no way to kill it.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    # Nullable on purpose: registration creates the account and onboarding sets
    # the name a moment later, so NULL is exactly the "not onboarded yet" signal
    # the frontend guard reads. Accounts that predate onboarding were backfilled.
    display_name = Column(String(DISPLAY_NAME_MAX), nullable=True)
    # A path into the uploads volume, set only by the avatar route. Never
    # accepted from a request body — the delete path unlinks whatever it points
    # at, so a client-supplied value let one user delete another's files.
    avatar = Column(Text, nullable=True)
    # An instructor's personal enrolment code, minted at registration. NULL for
    # students. Unique because a student registering quotes it to be linked.
    invite_code = Column(String(ID_LENGTH), nullable=True, unique=True)
    # Self-referential: the instructor whose code this student registered with.
    # SET NULL rather than CASCADE — deleting an instructor must not delete the
    # students' accounts and their history along with them.
    instructor_id = Column(String(ID_LENGTH), ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)
