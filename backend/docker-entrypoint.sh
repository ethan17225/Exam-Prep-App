#!/bin/sh
set -e

# Wait for Postgres, then bring the schema to head. Any failure here exits
# non-zero so the container crash-loops rather than serving a half-migrated
# schema. psycopg3 is dual-mode, so this sync engine shares the app's URL.
python - <<'PY'
import os
import time

from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL is not set")

engine = create_engine(url)

last_error = None
for _ in range(60):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception as exc:  # noqa: BLE001 - report the real cause, whatever it is
        last_error = exc
        time.sleep(1)
else:
    engine.dispose()
    raise SystemExit(f"Could not connect to the database after 60s: {last_error}")

engine.dispose()
PY

alembic upgrade head

# gunicorn supervises N uvicorn workers. Each worker holds its own pool of
# (DB_POOL_SIZE + DB_MAX_OVERFLOW) = 15 connections, so keep
#   WEB_CONCURRENCY * 15 + a few  <  Postgres max_connections (default 100).
# Raising WEB_CONCURRENCY past ~5 needs max_connections raised to match.
#
# --forwarded-allow-ips trusts X-Forwarded-* headers. Uvicorn's proxy middleware
# only matches exact IPs or '*', not CIDR, and the frontend container's IP is not
# stable — so '*' is the practical value. It is bounded by the compose network
# split (see docker-compose.yml): only the frontend and backup containers can
# reach this service, so no untrusted peer is in a position to forge the header.
# The app does not use the client IP for authorization in any case.
exec gunicorn src.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WEB_CONCURRENCY:-3}" \
    --bind 0.0.0.0:8000 \
    --timeout 90 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
