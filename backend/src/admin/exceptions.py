from src.exceptions import DetailedHTTPException


class StudentNotFound(DetailedHTTPException):
    # Also raised for a real account that belongs to a different instructor. A 403
    # there would confirm the id exists, which is an enumeration oracle over every
    # account in the deployment.
    STATUS_CODE = 404
    DETAIL = "Student not found"
