from pydantic import BaseModel


class DocumentOut(BaseModel):
    filename: str
    title: str
    pdf_url: str
    html_url: str | None
    size_bytes: int
    course_id: str | None
    course_name: str


class DocumentContentOut(BaseModel):
    title: str
    html: str
