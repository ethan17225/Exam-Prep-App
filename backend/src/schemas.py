"""Response primitives shared by more than one domain.

Anything used by a single domain belongs in that domain's `schemas.py`.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, PlainSerializer


def _iso_utc(value: datetime) -> str:
    """Wire format for API timestamps.

    Services store naive datetimes from `datetime.now()` (UTC in Docker). A
    bare `.isoformat()` has no offset, so browsers parse it as *local* and shift
    exam clocks by the client UTC offset. Tag naive values as UTC with `Z`.
    """
    if value.tzinfo is not None:
        return value.isoformat()
    return value.isoformat() + "Z"


# One datetime convention for the whole API. Naive values are UTC; aware values
# keep their offset. Always go through this annotation — never hand-roll
# `.isoformat()` in a service.
ISODateTime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]


class DeletedOut(BaseModel):
    deleted: bool


class TopicStatOut(BaseModel):
    topic: str
    total: int
    correct: int
    score: int


class DailyPointOut(BaseModel):
    day: str
    attempts: int
    average_score: float


class StudentAttemptOut(BaseModel):
    """An attempt as a staff member sees it — deliberately without the `results`
    blob, since listing those is what made the student-facing history endpoint a
    multi-megabyte response.

    Shared by the instructor drill-down and the admin's user drill-down, which is
    why it lives here rather than in either domain.
    """

    id: str
    exam_id: str
    exam_title: str
    score: float
    correct: int
    total: int
    passed: bool
    pass_grade: int
    mode: str
    over_time: bool
    time_spent_seconds: int
    taken_at: ISODateTime
