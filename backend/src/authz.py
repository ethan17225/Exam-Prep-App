from typing import TYPE_CHECKING

from sqlalchemy import or_
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.elements import ColumnElement

if TYPE_CHECKING:  # keeps this module a true runtime leaf, so it can never cycle
    from src.auth.models import User


def visible(model: type[DeclarativeBase], user: "User") -> ColumnElement[bool]:
    """Read predicate for owned content: shared with everyone, or mine.

    Applied identically for instructors — a role bypass here is where a leak
    would eventually live. Visibility is frozen at creation time, so promoting a
    student never retroactively publishes their private drafts.

    Mutation is a separate question: see `exams.service.get_owned_exam_or_404`.
    """
    return or_(model.is_shared.is_(True), model.owner_id == user.id)
