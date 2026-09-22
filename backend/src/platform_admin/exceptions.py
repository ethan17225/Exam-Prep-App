from src.exceptions import DetailedHTTPException


class AccountNotFound(DetailedHTTPException):
    STATUS_CODE = 404
    DETAIL = "Account not found"


class InstructorNotFound(DetailedHTTPException):
    # Raised when the *referenced* instructor is missing or is not staff, e.g.
    # enrolling a student with an id that belongs to another student.
    STATUS_CODE = 404
    DETAIL = "Instructor not found"


class OwnerNotStaff(DetailedHTTPException):
    # Content owned by a student is private forever (visibility is frozen at
    # creation), so transferring shared material to one would silently hide it.
    STATUS_CODE = 409
    DETAIL = "Content can only be transferred to an instructor or an admin"


class SelfActionRefused(DetailedHTTPException):
    """Refuses the two actions an admin could use to lock everyone out.

    An admin may not change their own role or delete their own account. That pair
    of rules is what guarantees at least one admin always exists: every other
    account is demotable, but the caller doing the demoting is never a candidate,
    so the set can never reach empty. It is also why there is no separate
    "last admin" check to keep in sync.
    """

    STATUS_CODE = 409
    DETAIL = "You cannot change your own role or delete your own account"


class ImpersonateSelfRefused(DetailedHTTPException):
    STATUS_CODE = 409
    DETAIL = "You cannot impersonate your own account"


class ImpersonateAdminRefused(DetailedHTTPException):
    STATUS_CODE = 403
    DETAIL = "You cannot impersonate another admin"


class AlreadyImpersonating(DetailedHTTPException):
    STATUS_CODE = 409
    DETAIL = "End the current impersonation session before starting another"


class NotImpersonating(DetailedHTTPException):
    STATUS_CODE = 409
    DETAIL = "You are not currently impersonating anyone"


class StudentHasNoInstructor(DetailedHTTPException):
    STATUS_CODE = 422
    DETAIL = "A student must be enrolled with an instructor"


class ReassignToSameInstructor(DetailedHTTPException):
    STATUS_CODE = 422
    DETAIL = "Choose a different instructor to move the students to"
