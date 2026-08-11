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

# gunicorn supervises N uvicorn workers. --proxy-headers keeps client IPs from
# nginx; --forwarded-allow-ips trusts the compose network in front of us.
exec gunicorn src.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WEB_CONCURRENCY:-3}" \
    --bind 0.0.0.0:8000 \
    --timeout 90 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --forwarded-allow-ips '*'
