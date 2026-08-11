# .svg is deliberately absent: SVGs are served from the same origin as the app,
# so a script inside one is stored XSS. This is a security decision, which is why
# it lives here and not in config.py where an env var could widen it.
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Question images are served under /api/... so the dev proxy and nginx forward
# them without extra rules.
UPLOADS_URL_PREFIX = "/api/uploads"
