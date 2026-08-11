from fastapi import Request

from src.auth.constants import AUTH_COOKIE


def bearer_token(request: Request) -> str | None:
    """Token from the Authorization header, falling back to the auth cookie.

    Pure header parsing with no database access, so both the `get_current_user`
    dependency and the static-mount middleware can share it.
    """
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return request.cookies.get(AUTH_COOKIE)
