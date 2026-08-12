from src.exceptions import DetailedHTTPException


class NotAuthenticated(DetailedHTTPException):
    STATUS_CODE = 401
    DETAIL = "Not authenticated"


class InvalidToken(DetailedHTTPException):
    STATUS_CODE = 401
    DETAIL = "Invalid or expired token"


class BadCredentials(DetailedHTTPException):
    # Same message whether the email exists or the password is wrong — do not
    # leak which accounts exist.
    STATUS_CODE = 401
    DETAIL = "Incorrect email or password"


class InstructorRequired(DetailedHTTPException):
    STATUS_CODE = 403
    DETAIL = "Instructor access required"


class RegistrationClosed(DetailedHTTPException):
    STATUS_CODE = 403
    DETAIL = "Registration is closed"


class InvalidInviteCode(DetailedHTTPException):
    STATUS_CODE = 403
    DETAIL = "Invalid invite code"


class EmailTaken(DetailedHTTPException):
    STATUS_CODE = 409
    DETAIL = "An account with that email already exists"


class UnsupportedAvatarType(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Unsupported image type"


class AvatarTooLarge(DetailedHTTPException):
    STATUS_CODE = 413
    DETAIL = "Image is too large"
