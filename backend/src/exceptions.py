from fastapi import HTTPException


class DetailedHTTPException(HTTPException):
    """Base for every domain exception.

    Subclasses `HTTPException` rather than replacing it, deliberately: the
    frontend reads `err.error.detail` on every failed request, so responses must
    stay byte-identical to the hand-written `HTTPException(404, "...")` calls
    this replaces. Carrying the code and message as class attributes keeps that
    guarantee without a single exception handler.
    """

    STATUS_CODE: int = 500
    DETAIL: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(status_code=self.STATUS_CODE, detail=detail or self.DETAIL)
