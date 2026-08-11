# MCQ Exam App

A minimalist web app for taking MCQ, Select All That Apply (SATA), and Fill in the Blank (FIB) exams.

## Tech Stack

- **Frontend:** Angular 21
- **Backend:** FastAPI (Python) with SQLAlchemy + PostgreSQL 16

## Quick Start

### Docker (everything at once)

```bash
cp .env.example .env
# Fill in POSTGRES_PASSWORD, AUTH_SECRET, AUTH_INVITE_CODE, BOOTSTRAP_ADMIN_*
# Generate secrets: python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build
```

Set `APP_DOMAIN` to your hostname and Caddy fetches a Let's Encrypt certificate
automatically; leave it as `:80` for a local run. The app is served through
Caddy on ports 80/443. Compose refuses to start if a required secret is unset.

The first instructor account is created by the database migration from
`BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` — sign in with it and
change the password. Everyone else registers with the `AUTH_INVITE_CODE`.
Nothing else can mint an instructor, so that migration is not optional.

### Or run the pieces yourself

#### 1. Backend

Needs PostgreSQL. Copy `backend/.env.example` to `backend/.env` and fill it in.

```bash
cd backend
pip3 install -r requirements.txt
alembic upgrade head          # creates the schema and the first instructor
uvicorn src.main:app --port 8000 --reload
```

API runs at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`
when `ENVIRONMENT` is `local` or `staging`; disabled otherwise.

`DATABASE_URL` must use the `postgresql+psycopg://` scheme — the app runs on
SQLAlchemy's async engine, and a bare `postgresql://` URL selects a sync driver
that it will refuse.

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

### Practice vs. graded exams

Every exam is one or the other, set by `allow_practice` (instructor-created
exams default to graded, student-created to practice; either owner can flip it):

- **Practice** reveals the answer key to the student — that is the point. Never
  grade an exam that has practice enabled; its key is available to anyone who can
  see it.
- **Graded** withholds the key until submission and enforces the whole attempt
  server-side: one open attempt at a time, the time limit and elapsed clock are
  the server's, and the score is computed from what the server received (client
  self-marking and question-subset selection are ignored). Submitting is
  at-most-once.

### What graded mode does *not* protect against

Written down so nobody mistakes it for lockdown proctoring:

- It is **not** proctoring software — no screen lock, no second-device
  detection. A student can read the paper on another device or get help.
- A student **owns any exam they upload**, including a re-upload of the
  instructor's material, and therefore owns its key.
- **Attempts are unlimited.** Submitting frees the slot, so a student can retake;
  every attempt appears in History for the instructor to see, but "best score" is
  theirs to pick. Blocking retakes needs an instructor reset flow (not built).
- An exam with **no time limit has no deadline** — set one for anything
  invigilated.
- **Graded fill-in-the-blank is exact/numeric match** (no fuzzy matching, no
  manual regrade). Prefer multiple-choice on assessments.
- An abandoned graded attempt is cleared by an instructor via
  `DELETE /api/admin/in-progress/{id}` — students cannot discard their own (that
  would reset the timer).

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
The dumps are **plaintext and contain password hashes and answer keys** — the
`./backups` directory must be treated as a secret (it is gitignored). For an
untrusted host, pipe the dump through `age`/`gpg` with a public key and store the
private key elsewhere. To restore:

```bash
gunzip -c backups/mcq_app_<timestamp>.sql.gz | docker compose exec -T db psql -U postgres mcq_app
```

## Tests

```bash
cd backend
pip3 install -r requirements-dev.txt

pytest                 # auth primitives, route guards, input validation — no DB needed
ruff check src tests && ruff format --check src tests

# The one test that exercises real queries. Needs a running server and an account.
API_BASE=http://localhost:8000/api E2E_EMAIL=... E2E_PASSWORD=... python tests/e2e_live.py
```

`tests/e2e_live.py` creates and then deletes an exam titled `__e2e_smoke_test__`.
Use `http://localhost:8001/api` for the Docker mapping.

## Backend layout

Organised by domain, one package per bounded context:

```
backend/src/
├── auth/        users, JWT, the CurrentUserDep/InstructorDep dependencies
├── courses/     course CRUD
├── exams/       Exam + Question, exam CRUD, the question editor, image uploads
├── attempts/    in-progress autosave, submit, history
├── documents/   filesystem-backed course PDFs (no table)
├── admin/       the instructor dashboard (a cross-domain read view)
├── grading/     answer grading — a pure leaf, imported by three domains
└── main.py      app assembly, static mounts, /healthz
```

Conventions and the invariants that keep the import graph acyclic are documented
in `.claude/skills/exam-api-practices/SKILL.md`.

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
