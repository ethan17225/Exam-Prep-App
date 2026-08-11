from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.database import Base


class Course(Base):
    __tablename__ = "course"
    __table_args__ = (
        # Course names are unique per owner, not globally.
        UniqueConstraint("owner_id", "name"),
        Index(None, "owner_id"),
    )

    id = Column(String(8), primary_key=True)
    owner_id = Column(String(8), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    # Set server-side from the creator's role; never accepted from the client.
    is_shared = Column(Boolean, nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)

    exams = relationship("Exam", back_populates="course")
