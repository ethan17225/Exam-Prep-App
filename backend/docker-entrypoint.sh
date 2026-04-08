#!/bin/sh
set -e
python - <<'PY'
import os
import time
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL is not set")

for i in range(60):
    try:
        eng = create_engine(url)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("Could not connect to the database")
PY

python seed.py
exec uvicorn main:app --host 0.0.0.0 --port 8000
