#!/bin/sh
set -e

# Wait for Postgres, then bring the schema to head. Any failure here exits non-zero
# so the container crash-loops rather than serving a half-migrated schema.
python - <<'PY'
import os
import time

from sqlalchemy import create_engine, inspect, text

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

# Baseline any database that predates Alembic: it already has the 0001 schema
# (created by the old create_all + ALTER guards), so stamp it instead of running 0001.
tables = set(inspect(engine).get_table_names())
if "alembic_version" not in tables and "courses" in tables:
    print("Pre-Alembic database detected — stamping baseline 0001", flush=True)
    from alembic import command
    from alembic.config import Config

    command.stamp(Config("alembic.ini"), "0001")

engine.dispose()
PY

alembic upgrade head

# gunicorn supervises N uvicorn workers: routes are sync `def`, so one worker
# pinned the app to a single core. --proxy-headers keeps client IPs from nginx.
exec gunicorn main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WEB_CONCURRENCY:-3}" \
    --bind 0.0.0.0:8000 \
    --timeout 90 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --forwarded-allow-ips '*'
