from src.exceptions import DetailedHTTPException


class RecordNotFound(DetailedHTTPException):
    # Shared by the in-progress and history routes: both returned this exact
    # string before the refactor, and the frontend shows `detail` verbatim.
    STATUS_CODE = 404
    DETAIL = "Record not found"


class NoValidQuestions(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "No valid questions selected"


class AttemptNotOpen(DetailedHTTPException):
    # 409 rather than 404: the exam exists and is visible; it is the attempt that
    # is missing, usually because it was already submitted.
    STATUS_CODE = 409
    DETAIL = "No open attempt for this exam. It may already have been submitted — check History."


class AttemptExpired(DetailedHTTPException):
    STATUS_CODE = 409
    DETAIL = "Time is up for this attempt. Submit now — answers are no longer being saved."


class AttemptNotDiscardable(DetailedHTTPException):
    STATUS_CODE = 403
    DETAIL = "A graded attempt cannot be discarded. Submit it, or ask an instructor to reset it."


class PracticeDisabled(DetailedHTTPException):
    # Not a 404: the exam is visible to this caller, so there is no existence
    # oracle here — only a forbidden action.
    STATUS_CODE = 403
    DETAIL = "Practice mode is disabled for this exam"


class ExamIdMismatch(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Submission exam_id does not match the exam being submitted"
