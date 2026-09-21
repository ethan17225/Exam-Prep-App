from src.exceptions import DetailedHTTPException


class ExamNotFound(DetailedHTTPException):
    STATUS_CODE = 404
    DETAIL = "Exam not found"


class ExamNotOwned(DetailedHTTPException):
    STATUS_CODE = 403
    DETAIL = "You do not own this exam"


class QuestionNotFound(DetailedHTTPException):
    STATUS_CODE = 404
    DETAIL = "Question not found"


class EmptyTitle(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Title cannot be empty"


class AttemptLargerThanBank(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Questions per attempt cannot exceed the questions available in the mix"


class UnsupportedImageType(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Unsupported image type"


class ImageTooLarge(DetailedHTTPException):
    STATUS_CODE = 413
    DETAIL = "Image is too large"
