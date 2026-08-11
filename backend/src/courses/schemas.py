from pydantic import BaseModel, ConfigDict, Field

from src.schemas import ISODateTime


class CourseCreate(BaseModel):
    name: str = Field(max_length=255)


class CourseOut(BaseModel):
    # Populated straight from the ORM row, so attribute access must be allowed.
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: ISODateTime
