from src.exceptions import DetailedHTTPException


class CourseNameEmpty(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Course name cannot be empty"


class CourseNameTaken(DetailedHTTPException):
    STATUS_CODE = 409
    DETAIL = "A course with this name already exists"


class CourseNotFound(DetailedHTTPException):
    STATUS_CODE = 404
    DETAIL = "Course not found"
