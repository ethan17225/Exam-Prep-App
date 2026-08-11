from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class CourseCreate(BaseModel):
    name: str = Field(max_length=255)


class CourseOut(BaseModel):
    # Populated straight from the ORM row, so attribute access must be allowed.
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime

    @field_serializer("created_at")
    def _iso(self, value: datetime) -> str:
        # The frontend parses these as ISO strings; datetimes are naive local.
        return value.isoformat()
