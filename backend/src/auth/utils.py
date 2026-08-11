from fastapi import Request

from src.auth.constants import AUTH_COOKIE


def bearer_token(request: Request) -> str | None:
    """Token from the `Authorization` header. Pure parsing, no database access."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def static_mount_token(request: Request) -> str | None:
    """Token for the two StaticFiles mounts, which also accept the auth cookie.

    Only these mounts fall back to the cookie, and deliberately so: they are
    loaded by `<img src>` and `<a href>`, which cannot carry a header. Every
    `/api/*` route requires the bearer token instead, so a cookie alone can never
    perform a state-changing request — the app does not rely on SameSite as its
    only CSRF defence.
    """
    return bearer_token(request) or request.cookies.get(AUTH_COOKIE)
