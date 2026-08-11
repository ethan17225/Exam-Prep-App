# MCQ Exam App

A minimalist web app for taking MCQ, Select All That Apply (SATA), and Fill in the Blank (FIB) exams.

## Tech Stack

- **Frontend:** Angular 21
- **Backend:** FastAPI (Python) with SQLAlchemy + PostgreSQL 16

## Quick Start

### Docker (everything at once)

```bash
cp .env.example .env
# Fill in POSTGRES_PASSWORD, JWT_SECRET, INVITE_CODE, BOOTSTRAP_ADMIN_*
# Generate secrets: python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build
```

Set `APP_DOMAIN` to your hostname and Caddy fetches a Let's Encrypt certificate
automatically; leave it as `:80` for a local run. The app is served through
Caddy on ports 80/443. Compose refuses to start if a required secret is unset.

The first instructor account is created by the database migration from
`BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` — sign in with it and
change the password. Everyone else registers with the `INVITE_CODE`.

### Or run the pieces yourself

#### 1. Backend

Needs PostgreSQL. Copy `backend/.env.example` to `backend/.env` and fill it in.

```bash
cd backend
pip3 install -r requirements.txt
alembic upgrade head          # creates the schema and the first instructor
uvicorn main:app --port 8000 --reload
```

API runs at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

#### 2. Frontend

```bash
cd frontend
npm install
npx ng serve
```

App runs at `http://localhost:4200` and proxies `/api` to port 8000.

## Accounts and access

- **Students** register with the invite code. They see the shared question bank
  plus anything they create themselves; their attempts and history are private.
- **Instructors** create content that is visible to everyone, and get the Admin
  dashboard showing every student's in-progress attempts.
- Only the owner of an exam can edit or delete it, shared or not.

> **Known limitation:** `GET /api/exams/{id}?include_answers=true` is available
> to anyone who can see the exam, because practice mode grades client-side. A
> determined student can read the answer key from devtools. Closing this means
> moving reveal/check-answer to server calls.

## Database migrations

Schema changes go through Alembic; nothing runs DDL at import time.

```bash
cd backend
alembic revision --autogenerate -m short_slug   # review the generated file
alembic upgrade head
```

Databases created before Alembic are stamped automatically on first start.

## Backups

The compose stack dumps the database daily to `./backups/` and keeps 14 days.
To restore:

```bash
gunzip -c backups/mcq_app_<timestamp>.sql.gz | docker compose exec -T db psql -U postgres mcq_app
```

## Tests

```bash
cd backend
python test_auth.py    # auth primitives — no DB or server needed
python test_api.py     # route guards and input validation — no DB or server needed
API_BASE=http://localhost:8000/api E2E_EMAIL=... E2E_PASSWORD=... python test_e2e.py
```

`test_e2e.py` runs against a live server and creates then deletes a temporary
exam. Use `http://localhost:8001/api` for the Docker mapping.

## Features

- **Upload** — Paste or upload a JSON file with exam questions
- **Exams** — Browse and start available exams
- **Timer** — Elapsed time clock during exam-taking
- **Question types** — MCQ (single choice), SATA (multi-select), FIB (text input),
  plus the Next-Gen NCLEX style types: MATRIX, CLOZE, BOWTIE, RANKING, HIGHLIGHT, HOTSPOT
- **Question navigator** — Jump to any question, flag questions for review
- **Results** — Detailed review with correct/incorrect highlighting and rationales
- **History** — View all past test attempts with scores
- **Pass threshold** — 72% required to pass (`PASS_THRESHOLD` in `backend/main.py`)

## JSON Format

```json
[
  {
    "number": 1,
    "topic": "Topic name",
    "type": "MCQ",
    "question": "Your question here?",
    "options": ["A. Option 1", "B. Option 2", "C. Option 3", "D. Option 4"],
    "answer": "C",
    "rationale": "Explanation here."
  },
  {
    "number": 2,
    "topic": "Topic name",
    "type": "SATA",
    "question": "Select all that apply.",
    "options": ["A. Option 1", "B. Option 2", "C. Option 3"],
    "answer": ["A", "C"],
    "rationale": "Explanation here."
  },
  {
    "number": 3,
    "topic": "Topic name",
    "type": "FIB",
    "question": "The answer is ___.",
    "answer": "answer text",
    "rationale": "Explanation here."
  }
]
```
