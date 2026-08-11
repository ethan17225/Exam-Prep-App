from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"


JWT_ALGORITHM = "HS256"

# The same JWT is mirrored into this cookie at login, purely so <img src> and
# <a href> requests to the two StaticFiles mounts authenticate — those cannot
# carry an Authorization header.
AUTH_COOKIE = "exam_token"
