from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    # Platform administrator. A third role, not a superset of either of the
    # others: it fails the instructor gate and has no class and no attempts of
    # its own. `/api/platform/*` accepts nobody else. Unreachable from
    # RegisterIn — see auth/schemas.py.
    ADMIN = "admin"


# Who publishes shared content, holds an enrolment code, and may be a student's
# instructor. Admin is absent on purpose: an admin does not teach a class.
STAFF_ROLES = frozenset({UserRole.INSTRUCTOR})

# What `POST /api/auth/register` is allowed to mint. ADMIN's absence is the whole
# point: the student branch of `register` accepts any role it is handed, so
# leaving admin in would let anyone holding an instructor's enrolment code sign
# themselves up as one. Admins are created only by another admin.
REGISTRABLE_ROLES = frozenset({UserRole.STUDENT, UserRole.INSTRUCTOR})

JWT_ALGORITHM = "HS256"

# The same JWT is mirrored into this cookie at login, purely so <img src> and
# <a href> requests to the two StaticFiles mounts authenticate — those cannot
# carry an Authorization header.
AUTH_COOKIE = "exam_token"
