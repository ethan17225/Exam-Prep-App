from src.exceptions import DetailedHTTPException


class RecordNotFound(DetailedHTTPException):
    # Shared by the in-progress and history routes: both returned this exact
    # string before the refactor, and the frontend shows `detail` verbatim.
    STATUS_CODE = 404
    DETAIL = "Record not found"


class NoValidQuestions(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "No valid questions selected"
