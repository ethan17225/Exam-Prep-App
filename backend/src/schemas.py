"""Response primitives shared by more than one domain.

Anything used by a single domain belongs in that domain's `schemas.py`.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

# One datetime convention for the whole API. Timestamps are naive local time
# (see the `datetime.now()` convention in the services), and `.isoformat()` on a
# naive datetime renders exactly what the hand-written serializers produced
# before — the wire format must not shift.
ISODateTime = Annotated[datetime, PlainSerializer(lambda v: v.isoformat(), return_type=str)]


class DeletedOut(BaseModel):
    deleted: bool
