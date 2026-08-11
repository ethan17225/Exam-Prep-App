---
name: exam-api-practices
description: Project-tailored FastAPI conventions for the Exam-Prep-App backend. Use when adding or changing endpoints, Pydantic schemas, SQLAlchemy models, domain packages, grading logic, question types, Alembic migrations, or tests in backend/.
---

# Exam API Practices (project-tailored)

Single source of truth for backend conventions. Everything below describes what
`backend/src/` actually does. Frontend conventions live in the sibling
`exam-ui-practices` skill.

## Stack

| Concern     | Choice                                                | Do NOT use                                              |
|-------------|-------------------------------------------------------|---------------------------------------------------------|
| Python      | 3.12 (`backend/Dockerfile`)                            |                                                         |
| FastAPI     | 0.115+, `Annotated[T, Depends(...)]` everywhere        | default-argument `= Depends(...)` / `= Query(...)`      |
| Validation  | Pydantic 2 + pydantic-settings, one config per domain  | a single app-wide settings object                       |
| ORM         | SQLAlchemy 2.0 **async** — `select()`, `AsyncSession`  | `db.query(...)` 1.x style, sync sessions                |
| Driver      | **psycopg3** (`postgresql+psycopg://`)                 | psycopg2, asyncpg (see below)                           |
| DB          | PostgreSQL 16, JSONB                                   | SQLite (JSONB is load-bearing)                          |
| Migrations  | Alembic, async template. DDL never runs at import time | `create_all`, import-time `ALTER TABLE`                 |
| Auth        | PyJWT + bcrypt directly, 12h bearer token              | python-jose, passlib, refresh tokens                    |
| Tests       | pytest + pytest-asyncio + httpx `AsyncClient`          | `TestClient`, `httpx` (the package is **`httpx2`**)     |
| Lint        | ruff (`ruff.toml`, py312, line-length 120)             | black/isort/flake8                                      |
| Server      | gunicorn + UvicornWorker, `src.main:app`               | bare single-worker uvicorn                              |

**psycopg3, not asyncpg** — deliberate. It is dual-mode, so the same URL backs
`create_async_engine` (the app) and `create_engine` (the entrypoint's wait loop
and Alembic tooling); it ships a pure-Python wheel that works on Python 3.14, so
tests run locally; and it returns JSONB from raw `text()` queries as dicts rather
than strings. asyncpg is measurably faster and this app is nowhere near
driver-bound.

## Layout — one package per bounded context

```
src/
├── main.py         app assembly, static mounts, middleware, /healthz
├── config.py       global Settings (no env_prefix) + BASE_DIR
├── database.py     async engine, session factory, Base + naming convention
├── models.py       Alembic import manifest — NOT shared bases
├── exceptions.py   DetailedHTTPException
├── authz.py        visible(model, user)
├── constants.py    MAX_INT, MAX_QUESTIONS_PER_EXAM
├── auth/           9 files — the reference domain
├── courses/        models, schemas, service, exceptions, router
├── exams/          Exam + Question, two APIRouters, no dependencies.py
├── attempts/       InProgressExam + History, three APIRouters
├── documents/      no models (filesystem-backed)
├── admin/          router + service only
└── grading/        constants, utils, service — a pure leaf
```

**Do not create a domain file until it has content.** The template implies nine
files per domain; ~32 of those should not exist here. An empty `utils.py` becomes
a grab-bag within a month.

**No `src/health/`.** One 6-line readiness probe with no model, schema or
business logic lives in `main.py`. `/healthz` has **no `/api` prefix** — the
Dockerfile `HEALTHCHECK` and the frontend's `depends_on: service_healthy` both
hit that exact path.

### The invariants that keep this working

**1. Every `__init__.py` stays empty.** One convenience re-export
(`from .router import router`) turns the acyclic graph into a partially
initialized import error. This is the highest-value rule in the file.

**2. Imports only point down this layering:**

```
L0  config · database · exceptions · authz · constants · grading/*
L1  auth      L2  courses      L3  exams, documents
L4  attempts  L5  admin        L6  main
```

**3. `service.py` may only import a strictly lower `service.py`. Any edge that
would point up gets hoisted into `router.py`**, which nothing imports but
`main.py`. There is exactly one such edge today: `exams/router.py` calls
`attempts_service.rename_exam(...)` because `attempts` owns the denormalized
`exam_title` copies. `exams/service.py` must never import `attempts`.

**4. No `models.py` imports another `models.py`.** `ForeignKey("user.id")` and
`relationship("User")` are strings resolved from the shared registry, so every
model module imports only `src.database`. Cross-domain services compose other
services rather than importing foreign models — `admin/service.py` imports zero
models.

**5. Cross-domain imports use the module, never a deep path:**
`from src.exams import service as exams_service`.

## Endpoints — the house shape

```python
router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.post(
    "",
    response_model=CourseOut,
    summary="Create a course",
    description="Creates a course owned by the caller.",
    responses={status.HTTP_409_CONFLICT: {"description": CourseNameTaken.DETAIL}},
)
async def create_course(payload: CourseCreate, user: CurrentUserDep, db: SessionDep):
    return await service.create(payload, user, db)
```

- `async def` everywhere. The only sync functions are pure CPU helpers that get
  handed to `run_in_threadpool`.
- `user: CurrentUserDep` (or `InstructorDep`) then `db: SessionDep`. Both are
  `Annotated` aliases — never `= Depends(...)`.
- Use `""` as the path for a router's root, not `"/"`, or the URL gains a
  trailing slash and the frontend 307s.
- Every route carries `response_model`, `summary`, `description` and a
  `responses` entry per failure mode. The route body stays thin; logic is in
  `service.py`.
- Fixed paths are declared **before** parameterized siblings in the same router
  (`/by-exam/{exam_id}` before `/{record_id}`; `/topic-stats` before
  `/{record_id}`). A test asserts this — breaking it is a silent 404.

### Ownership helpers are functions, not dependencies

`get_visible_exam_or_404` / `get_owned_exam_or_404` stay plain service
functions. Making them `Annotated[Exam, Depends(...)]` is idiomatic FastAPI and
would change the contract: dependencies resolve **before** the request body is
validated, so a malformed PATCH on an exam you don't own would return 403 where
it returns 422 today. That is why `src/exams/dependencies.py` does not exist.

## Async and SQLAlchemy

| Sync 1.x (gone)                     | Async 2.0                                                  |
|-------------------------------------|------------------------------------------------------------|
| `db.query(M).filter(C).first()`     | `(await db.execute(select(M).where(C)))` + `.scalar_one_or_none()` |
| `db.query(M).filter(C).all()`       | `(await db.execute(...)).scalars().all()`                   |
| `db.query(A.x, A.y)`                | `(await db.execute(select(A.x, A.y).where(C))).all()`       |
| `db.commit()` / `refresh` / `delete`| **`await`** all of them                                     |
| `db.add(x)`                         | `db.add(x)` — still sync, no await                          |

- **`.scalars()` only when the select has exactly one entity or one column.** On
  a column-tuple select it silently discards every column but the first. Three
  places select column tuples on purpose: `exams.service._type_count_rows`,
  `questions_by_exam_ids`, and the topic-stats raw SQL.
- **`.unique()` on any `joinedload` result.** Required for collections, harmless
  otherwise, and nobody should have to re-derive which is which.
- **Never `asyncio.gather` over one `AsyncSession`** — it raises
  `InterfaceError: another operation is in progress`. Concurrent queries need
  two sessions.
- **Eager-load anything you will touch.** A lazy relationship access raises
  `MissingGreenlet`, not an N+1. `selectinload` for collections, `joinedload`
  for many-to-one. Note `db.refresh()` expires relationships *unconditionally*,
  which is why `exam_summary` re-queries the course instead of reading
  `exam.course`.
- `expire_on_commit=False` is set and is **mandatory** — the default expires
  every attribute at commit, and many routes read an object after committing it.
- Blocking work gets `run_in_threadpool`, wrapping **whole operations, never
  individual syscalls**: bcrypt (~250 ms CPU), the documents filesystem walk, the
  HTML read+regex, the upload write loop. No `aiofiles` — it is itself a
  threadpool wrapper and forces one hop per chunk.

## Schemas

- Bounds are not optional: every string field carries `max_length` matching its
  column, every int is bounded by `MAX_INT`. Without them the driver raises and
  the route 500s — and a 500 on submit costs a student their attempt.
- `QuestionIn.type` is a plain `str`, **not** the `QuestionType` enum: the
  documented JSON upload format allows arbitrary type strings and grading
  normalizes them.
- Response models fed by ORM rows need `model_config = ConfigDict(from_attributes=True)`.
- `GET /api/exams/{id}` pairs `ExamQuestionOut` with
  `response_model_exclude_unset=True` so `answer`/`rationale` are **absent**, not
  null, when `include_answers` is false — the frontend distinguishes the two.
- PATCH partial updates use `payload.model_fields_set` to tell "absent" from
  "explicitly null".

## Exceptions

Domain exceptions subclass `DetailedHTTPException`, which subclasses
`HTTPException`:

```python
class ExamNotFound(DetailedHTTPException):
    STATUS_CODE, DETAIL = 404, "Exam not found"
```

**Subclass, never replace.** The frontend reads `err.error.detail` on every
failed request, so the goal is byte-identical responses with zero exception
handlers. The one global handler exists only to turn unhandled 500s into JSON.

## Authorization

**Read predicate for content** (`Course`, `Exam`) — `authz.visible`:

```python
or_(model.is_shared.is_(True), model.owner_id == user.id)
```

Applied identically to instructors. **No role bypass** — visibility is frozen at
creation time so promoting a student never publishes their private drafts. Role
is consulted in exactly two places: setting `is_shared` at creation, and the
`/api/admin/dashboard` gate.

**Write rule, always separate:** mutation requires `owner_id == user.id` even for
shared content. `get_owned_exam_or_404` for writes, `get_visible_exam_or_404` for
reads — never one for the other.

`is_shared` is **never** accepted from the client.

**Attempts** filter strictly on `user_id`. The single exception is
`attempts.service.list_in_progress_unscoped`, named for what it is; its only
caller is the instructor-gated dashboard.

Because `history.exam_id` has no FK, **never `join(Exam)` on a history query** —
an inner join silently drops history for deleted exams.

Any route reaching a `Question` by bare id must join `Exam` and check
`owner_id` (`get_owned_question_or_404`): `question.id` is a serial integer and
trivially enumerable, unlike the 8-char ids everywhere else.

## Configuration

One `BaseSettings` per domain with an `env_prefix` (`AUTH_`, `EXAMS_`, `DOCS_`).
The **global** `Settings` has no prefix — prefixing it would rename
`DATABASE_URL`, which compose, the entrypoint, Alembic and the tests all read.

Wrap every settings instantiation so a missing value exits with guidance rather
than a raw `ValidationError` traceback.

**Runtime paths derive from `BASE_DIR` in `src/config.py`**, never from a domain
module's `__file__`. `BASE_DIR` is `backend/` = `/app`, which is where the
`uploads` and `docs` volumes mount. Deriving them locally would resolve to
`/app/src/exams/uploads` — inside the image layer, so uploads would vanish on the
next `--build`.

The `mkdir` calls stay in `main.py` next to the mounts: a filesystem side effect
at config-import time would fire during test collection.

## Migrations

Alembic owns the schema; **nothing runs DDL at import time.**

1. Edit the domain's `models.py`.
2. `alembic revision --autogenerate -m short_slug`, then **read the file** —
   autogenerate misses implicit uniques and never writes data backfills.
3. `alembic upgrade head`.

- Constraint and index names come from `POSTGRES_INDEXES_NAMING_CONVENTION` in
  `database.py`. Don't hand-name them differently in a revision, or autogenerate
  churns forever.
- Adding a NOT NULL column to a populated table is three steps in one revision:
  add nullable → backfill → `SET NOT NULL`. **Drop any `server_default` used to
  get there** — a lingering default turns "forgot to set `owner_id`" from a loud
  error into silent cross-user leakage.
- Add a unique constraint only after deduplicating.
- **`alembic upgrade head --sql` works with no database.** That offline render,
  diffed against `CreateTable` output from `Base.metadata`, is the way to verify
  a hand-written revision.
- Revision `0002` seeds the bootstrap instructor. Nothing else can mint one, so
  it is not optional.

## Testing

| File | Needs | Covers |
|---|---|---|
| `tests/test_auth.py` | nothing | hashing, token round-trip/expiry/forgery, the visibility predicate |
| `tests/test_api.py` | nothing | every route rejecting anonymous access, input bounds → 422, route ordering, error shape |
| `tests/e2e_live.py` | a live server | full question-type round trip against real data |

- The first two need **no database**: `get_db` constructs its session lazily, so
  a request rejected before any query never opens a connection. Writing `get_db`
  as `async with AsyncSessionLocal.begin()` would break that.
- `ASGITransport(app, raise_app_exceptions=False)` — the equivalent of
  `TestClient(raise_server_exceptions=False)`, and **not** the default.
- Swap dependencies with `app.dependency_overrides`, not monkeypatching. A sync
  lambda overriding an async dependency is supported — don't "fix" it.
- `filterwarnings = error::RuntimeWarning` is set on purpose: a forgotten
  `await` on a session method only ever surfaces as that warning, and on
  `submit` it would silently discard a student's attempt.
- `e2e_live.py` is deliberately not named `test_*` so pytest ignores it; it uses
  stdlib urllib against real HTTP, and `AsyncClient`'s cookie jar would silently
  neuter its "unauthenticated request is rejected" check.

## Anti-patterns (check every diff)

| Anti-pattern | Fix |
|---|---|
| A non-empty `__init__.py` | keep them empty — this one breaks the import graph |
| `service.py` importing a higher domain's `service.py` | hoist the call into `router.py` |
| A `router.py` importing another domain's `models`/`schemas` | call that domain's `service` |
| `models.py` importing another `models.py` | FK and relationship targets are strings |
| A route without `CurrentUserDep`/`InstructorDep` | every `/api` route except `/api/auth/*` takes one |
| A content query without `authz.visible(...)` | reads use the predicate; writes use `get_owned_*` |
| An attempt query without `user_id` | `in_progress_exam` and `history` are always caller-scoped |
| `is_shared` read from the request body | derive it from `user.role` |
| `if role == "instructor": skip the filter` | no visibility bypass; only the dashboard gate reads role |
| `.scalars()` on a column-tuple select | drops every column but the first, silently |
| Missing `await` on `commit`/`refresh`/`delete`/`execute` | silent data loss — the RuntimeWarning gate catches it |
| `asyncio.gather` over one session | two sessions, or run them sequentially |
| Reading a relationship that was not eager-loaded | `selectinload`/`joinedload`, or query it explicitly |
| `= Depends(...)` / `= Query(...)` default args | `Annotated[T, Depends()]` / `Annotated[T, Query()]` |
| A route without `response_model` and docs | every route is documented |
| A Pydantic field without a bound | `max_length` / `ge`/`le=MAX_INT` — else it's a 500 |
| Blocking work inside `async def` | `run_in_threadpool`, wrapping the whole operation |
| DDL or seeding at import time | an Alembic revision |
| A path derived from a domain module's `__file__` | derive from `BASE_DIR` |
| Returning a full list of `results` blobs | paginate; aggregate in SQL |
| `join(Exam)` in a history query | drops rows for deleted exams |
| A new domain file that is empty | don't create it until it has content |
