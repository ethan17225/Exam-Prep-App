from fastapi import FastAPI, HTTPException, Depends, Query, UploadFile, File, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, NamedTuple
from uuid import uuid4
import logging
import os
import pathlib
import bcrypt
import jwt
from sqlalchemy import or_, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload, selectinload

from database import get_db
from models import Course, Exam, Question, History, InProgressExam, User

# Schema is owned by Alembic and applied by docker-entrypoint.sh before this module
# is imported. Nothing here may run DDL or seed data at import time.

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise SystemExit("JWT_SECRET is not set — refusing to start with a guessable signing key")
if len(JWT_SECRET) < 32:
    raise SystemExit(
        "JWT_SECRET must be at least 32 characters (HMAC-SHA256 key length). "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
JWT_ALGORITHM = "HS256"
# Long-lived on purpose: exams run 90-180 minutes and there is no refresh token.
# A token expiring mid-exam is the one failure that costs a student their answers.
TOKEN_TTL = timedelta(hours=12)
AUTH_COOKIE = "exam_token"

# Registration is gated by a shared invite code: it keeps the open internet out
# without building email verification. Unset means registration is closed.
INVITE_CODE = os.getenv("INVITE_CODE")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mcq")

app = FastAPI(title="MCQ Exam API")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the traceback and answer with JSON.

    Starlette's default 500 is bare text/plain and is emitted outside
    CORSMiddleware, so the frontend's `err.error.detail` read comes back
    undefined and cross-origin callers see an opaque CORS error instead.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Must stay False while allow_origins is "*" — browsers reject the combination.
    # Prod is same-origin behind nginx and dev is same-origin through proxy.conf.json,
    # so the auth cookie is never a cross-origin request.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOCS_ROOT = pathlib.Path(__file__).resolve().parent / "Docs"
DOCS_ROOT.mkdir(exist_ok=True)

# Mount static file serving for the Docs folder (PDFs and HTML)
app.mount("/docs-files", StaticFiles(directory=str(DOCS_ROOT)), name="docs-files")

UPLOADS_ROOT = pathlib.Path(__file__).resolve().parent / "uploads"
UPLOADS_ROOT.mkdir(exist_ok=True)

# Question images are stored under /api/uploads so the frontend proxy forwards them
app.mount("/api/uploads", StaticFiles(directory=str(UPLOADS_ROOT)), name="uploads")

PASS_THRESHOLD = 0.72

# Next-Gen NCLEX style question types with structured options/answers
ADVANCED_TYPES = {"MATRIX", "CLOZE", "BOWTIE", "RANKING", "HIGHLIGHT", "HOTSPOT"}


class _TypeCountRow(NamedTuple):
    """Just enough of a Question for `_question_type_counts` to classify it,
    so listing exams never has to load the JSONB payloads."""

    type: str | None
    options: Any


def _question_type_counts(questions: list) -> tuple[int, int, int, int]:
    """Return (mcq, sata, fib, other) using the same rules as submit grading."""
    mcq = sata = fib = other = 0
    for q in questions:
        qtype = (q.type or "").strip().upper()
        if qtype in ADVANCED_TYPES:
            other += 1
        elif qtype == "SATA":
            sata += 1
        elif qtype in ("FIB", "FILL-IN-THE-BLANK") or not q.options:
            fib += 1
        else:
            mcq += 1
    return mcq, sata, fib, other


def _norm_str_set(values) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, (list, tuple, set)):
        return {str(v).strip() for v in values if str(v).strip()}
    s = str(values).strip()
    return {p.strip() for p in s.split(",") if p.strip()} if s else set()


def _norm_str_list(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        return [str(v).strip() for v in values]
    return [str(values).strip()]


def _grouped_answer_map(value) -> dict[str, set[str]]:
    """Normalize MATRIX/BOWTIE answers: dict of key -> set of selections."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, set[str]] = {}
    for k, v in value.items():
        selections = _norm_str_set(v)
        if selections:
            out[str(k).strip()] = selections
    return out


def _is_fib_question(q) -> bool:
    qtype = (q.type or "").strip().upper()
    if qtype in ADVANCED_TYPES:
        return False
    return qtype in ("FIB", "FILL-IN-THE-BLANK") or not q.options


def _grade_question(q, user_answer) -> bool:
    """Shared grading logic for all question types (except FIB self-marking)."""
    expected = q.answer
    qtype = (q.type or "").strip().upper()

    if qtype in ("MATRIX", "BOWTIE"):
        return _grouped_answer_map(user_answer) == _grouped_answer_map(expected)

    if qtype == "CLOZE":
        user_list = _norm_str_list(user_answer if isinstance(user_answer, list) else None)
        expected_list = _norm_str_list(expected)
        return len(user_list) == len(expected_list) and all(
            u.lower() == e.lower() for u, e in zip(user_list, expected_list)
        )

    if qtype == "RANKING":
        user_list = _norm_str_list(user_answer if isinstance(user_answer, list) else None)
        expected_list = _norm_str_list(expected)
        return len(user_list) == len(expected_list) and user_list == expected_list

    if qtype == "HIGHLIGHT":
        return _norm_str_set(user_answer) == _norm_str_set(expected)

    if qtype == "HOTSPOT":
        return bool(user_answer) and str(user_answer).strip() == str(expected).strip()

    if qtype == "SATA":
        return _norm_str_set(expected) == _norm_str_set(user_answer)

    if _is_fib_question(q):
        user_str = str(user_answer or "").strip().lower()
        expected_str = str(expected).strip().lower()
        try:
            return float(user_str) == float(expected_str)
        except (ValueError, TypeError):
            return (
                user_str == expected_str
                or (len(user_str) >= 3 and user_str in expected_str)
                or (len(expected_str) >= 3 and expected_str in user_str)
            )

    return str(user_answer or "").strip() == str(expected).strip()


# ── Health ────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    """Readiness probe. Actually touches the pool, because pool exhaustion —
    not process death — is the likely failure mode here."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB failure means not ready
        logger.exception("Health check failed")
        return JSONResponse({"status": "unhealthy"}, status_code=503)
    return {"status": "ok"}


# ── Auth ──────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    # bcrypt hard-limits input at 72 bytes; the schemas bound it there too.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))


def _create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user.id, "role": user.role, "iat": now, "exp": now + TOKEN_TTL},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _user_from_token(token: str, db: Session) -> User | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    return db.query(User).filter(User.id == payload.get("sub")).first()


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer_token(request) or request.cookies.get(AUTH_COOKIE)
    if not token:
        raise HTTPException(401, "Not authenticated")
    user = _user_from_token(token, db)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_instructor(user: CurrentUserDep) -> User:
    if user.role != "instructor":
        raise HTTPException(403, "Instructor access required")
    return user


InstructorDep = Annotated[User, Depends(require_instructor)]


@app.middleware("http")
async def protect_static_mounts(request: Request, call_next):
    """Authenticate the two StaticFiles mounts.

    FastAPI dependencies do not apply to mounts, but middleware runs before
    routing so it does. These URLs are loaded by <img src> and <a href>, which
    cannot carry an Authorization header — hence the cookie set at login.

    ponytail: authentication only, not per-file authorization. A logged-in user
    could fetch another's question image by guessing the 10-hex-char filename.
    Upgrade path is FileResponse routes with an owner lookup per file.
    """
    path = request.url.path
    if path.startswith("/docs-files") or path.startswith("/api/uploads"):
        token = _bearer_token(request) or request.cookies.get(AUTH_COOKIE)
        if not token:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        try:
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.InvalidTokenError:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
    # Only token decoding happens here — no blocking I/O, so async is safe.
    return await call_next(request)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    invite_code: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


def _user_to_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role}


def _login_response(user: User) -> JSONResponse:
    token = _create_token(user)
    response = JSONResponse({"token": token, "user": _user_to_dict(user)})
    # Mirrored into an HttpOnly cookie purely so <img>/<a> requests to the static
    # mounts authenticate; the app itself uses the Bearer token.
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=int(TOKEN_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if not INVITE_CODE:
        raise HTTPException(403, "Registration is closed")
    if payload.invite_code != INVITE_CODE:
        raise HTTPException(403, "Invalid invite code")

    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with that email already exists")

    user = User(
        id=str(uuid4())[:8],
        email=email,
        password_hash=_hash_password(payload.password),
        role="student",
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _login_response(user)


@app.post("/api/auth/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    # Same message either way — do not leak which emails exist.
    if not user or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return _login_response(user)


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(AUTH_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def read_me(user: CurrentUserDep):
    return _user_to_dict(user)


# ── Ownership helpers ─────────────────────────────────────────────

def _visible(model, user: User):
    """Read predicate for content: shared with everyone, or mine.

    Applied identically for instructors — a role bypass here is where a leak
    would eventually live. Visibility is frozen at creation time, so promoting a
    student never retroactively publishes their private drafts.
    """
    return or_(model.is_shared.is_(True), model.owner_id == user.id)


def get_visible_exam_or_404(exam_id: str, user: User, db: Session, with_questions: bool = False) -> Exam:
    query = db.query(Exam)
    if with_questions:
        # Otherwise `exam.questions` lazy-loads as a second query on every access.
        query = query.options(selectinload(Exam.questions))
    exam = query.filter(Exam.id == exam_id, _visible(Exam, user)).first()
    if not exam:
        raise HTTPException(404, "Exam not found")
    return exam


def get_owned_exam_or_404(exam_id: str, user: User, db: Session) -> Exam:
    """For mutations: being able to see a shared exam never implies being able to change it."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")
    if exam.owner_id != user.id:
        raise HTTPException(403, "You do not own this exam")
    return exam


# ── Pydantic schemas ─────────────────────────────────────────────

# Bounds below mirror the column widths in models.py and Postgres' 32-bit
# integer range. Without them an over-long title or an oversized int is a 500
# from the driver instead of a 422 — and on submit it loses the attempt.
MAX_INT = 2_147_483_647
MAX_QUESTIONS_PER_EXAM = 1000


class QuestionIn(BaseModel):
    number: int = Field(ge=0, le=MAX_INT)
    topic: str = Field(max_length=2000)
    type: str = Field(max_length=30)
    sections: Any = None
    question: str = Field(max_length=20000)
    options: Any = None
    answer: Any
    rationale: str = Field(default="", max_length=20000)
    image: str | None = Field(default=None, max_length=500)


class QuestionUpdate(BaseModel):
    number: int | None = Field(default=None, ge=0, le=MAX_INT)
    topic: str | None = Field(default=None, max_length=2000)
    type: str | None = Field(default=None, max_length=30)
    question: str | None = Field(default=None, max_length=20000)
    sections: Any = None
    options: Any = None
    answer: Any = None
    rationale: str | None = Field(default=None, max_length=20000)


class ExamCreate(BaseModel):
    title: str = Field(max_length=255)
    questions: list[QuestionIn] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    course_id: str | None = Field(default=None, max_length=8)
    time_limit_minutes: int | None = Field(default=None, ge=0, le=MAX_INT)


class ExamTitleUpdate(BaseModel):
    title: str = Field(max_length=255)

class ExamTimeLimitUpdate(BaseModel):
    time_limit_minutes: int | None = Field(default=None, ge=0, le=MAX_INT)


class AnswerSubmission(BaseModel):
    question_number: int = Field(ge=0, le=MAX_INT)
    answer: Any = None
    fib_correct: bool | None = None


class ExamSubmission(BaseModel):
    exam_id: str = Field(max_length=8)
    answers: list[AnswerSubmission] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    time_spent_seconds: int = Field(ge=0, le=MAX_INT)
    mode: str = Field(default="exam", max_length=10)
    question_numbers: list[int] | None = Field(default=None, max_length=MAX_QUESTIONS_PER_EXAM)


class SaveProgressPayload(BaseModel):
    exam_id: str = Field(max_length=8)
    mode: str = Field(default="exam", max_length=10)
    # Keys are question numbers. Constraining them here stops a non-numeric key
    # from wedging the admin dashboard's int() conversion for everyone.
    answers: dict[Annotated[int, Field(ge=0, le=MAX_INT)], Any]
    flagged: list[int] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    question_order: list[int] = Field(max_length=MAX_QUESTIONS_PER_EXAM)
    remaining_seconds: int = Field(ge=0, le=MAX_INT)
    current_page: int = Field(default=0, ge=0, le=MAX_INT)


# ── Course Endpoints ──────────────────────────────────────────────

class CourseCreate(BaseModel):
    name: str = Field(max_length=255)


@app.get("/api/courses")
def list_courses(user: CurrentUserDep, db: Session = Depends(get_db)):
    courses = db.query(Course).filter(_visible(Course, user)).order_by(Course.name).all()
    return [
        {"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()}
        for c in courses
    ]


@app.post("/api/courses")
def create_course(payload: CourseCreate, user: CurrentUserDep, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Course name cannot be empty")
    # Names are unique per owner now, so only my own courses can collide.
    existing = db.query(Course).filter(Course.owner_id == user.id, Course.name == name).first()
    if existing:
        raise HTTPException(409, "A course with this name already exists")
    course = Course(
        id=str(uuid4())[:8],
        owner_id=user.id,
        is_shared=user.role == "instructor",
        name=name,
        created_at=datetime.now(),
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return {"id": course.id, "name": course.name, "created_at": course.created_at.isoformat()}


# ── Document Endpoints ────────────────────────────────────────────

@app.get("/api/documents")
def list_documents(
    user: CurrentUserDep, course_id: str | None = Query(None), db: Session = Depends(get_db)
):
    """Scan Docs/<course>/pdf/ folders and return documents grouped by course.

    Documents live on disk with no per-user story — the folder name is matched
    against a course name. They are shared reading material for every logged-in
    user; only the course association is filtered by visibility.
    """
    courses = db.query(Course).filter(_visible(Course, user)).all()
    course_map = {c.name: {"id": c.id, "name": c.name} for c in courses}

    docs: list[dict] = []
    if not DOCS_ROOT.is_dir():
        return docs

    for course_dir in sorted(DOCS_ROOT.iterdir()):
        if not course_dir.is_dir():
            continue

        pdf_dir = course_dir / "pdf"
        html_dir = course_dir / "html"

        if not pdf_dir.is_dir():
            continue

        matched_course = course_map.get(course_dir.name)

        for pdf in sorted(pdf_dir.glob("*.pdf")):
            # Check for matching HTML file
            html_file = html_dir / (pdf.stem + ".html") if html_dir.is_dir() else None
            has_html = html_file is not None and html_file.is_file()

            doc = {
                "filename": pdf.name,
                "title": pdf.stem,
                "pdf_url": f"/docs-files/{course_dir.name}/pdf/{pdf.name}",
                "html_url": f"/docs-files/{course_dir.name}/html/{pdf.stem}.html" if has_html else None,
                "size_bytes": pdf.stat().st_size,
                "course_id": matched_course["id"] if matched_course else None,
                "course_name": matched_course["name"] if matched_course else course_dir.name,
            }
            docs.append(doc)

    if course_id:
        docs = [d for d in docs if d["course_id"] == course_id]

    return docs


@app.get("/api/documents/html")
def get_document_html(user: CurrentUserDep, path: str = Query(...)):
    """Read and return the raw HTML content of a document."""
    import urllib.parse

    decoded = urllib.parse.unquote(path)
    rel = decoded.removeprefix("/docs-files/").removeprefix("/")
    html_path = (DOCS_ROOT / rel).resolve()

    # Keep the resolved path inside Docs/ so "../" in the query cannot escape it
    if not html_path.is_relative_to(DOCS_ROOT.resolve()):
        raise HTTPException(404, "Document not found")

    if not html_path.is_file() or not html_path.suffix.lower() == ".html":
        raise HTTPException(404, "Document not found")

    html_content = html_path.read_text(encoding="utf-8")

    # Extract just the <body> content (strip <html>, <head>, <style>, etc.)
    import re
    body_match = re.search(r'<body[^>]*>(.*)</body>', html_content, re.DOTALL)
    body_html = body_match.group(1).strip() if body_match else html_content

    return {"title": html_path.stem, "html": body_html}


# ── Endpoints ─────────────────────────────────────────────────────

@app.post("/api/exams")
def create_exam(payload: ExamCreate, user: CurrentUserDep, db: Session = Depends(get_db)):
    if payload.course_id:
        course = db.query(Course).filter(
            Course.id == payload.course_id, _visible(Course, user)
        ).first()
        if not course:
            raise HTTPException(404, "Course not found")

    exam_id = str(uuid4())[:8]
    exam = Exam(
        id=exam_id,
        owner_id=user.id,
        is_shared=user.role == "instructor",
        title=payload.title,
        course_id=payload.course_id,
        time_limit_minutes=payload.time_limit_minutes,
        created_at=datetime.now()
    )
    db.add(exam)
    for q in payload.questions:
        db.add(Question(
            exam_id=exam_id,
            number=q.number,
            topic=q.topic,
            type=q.type,
            question=q.question,
            sections=q.sections,
            options=q.options,
            answer=q.answer,
            rationale=q.rationale,
            image=q.image,
        ))
    db.commit()
    return {"exam_id": exam_id, "total_questions": len(payload.questions)}


@app.get("/api/exams")
def list_exams(user: CurrentUserDep, course_id: str | None = Query(None), db: Session = Depends(get_db)):
    # joinedload on a collection produced a cartesian join that materialized every
    # question of every exam — including the JSONB payloads — purely to count them.
    # Only `type` and `options` are needed for the counts, so select just those.
    query = db.query(Exam).options(joinedload(Exam.course)).filter(_visible(Exam, user))
    if course_id:
        query = query.filter(Exam.course_id == course_id)
    exams = query.order_by(Exam.created_at).all()

    counts: dict[str, list] = {e.id: [] for e in exams}
    if counts:
        rows = db.query(Question.exam_id, Question.type, Question.options).filter(
            Question.exam_id.in_(counts.keys())
        )
        for exam_id, qtype, options in rows:
            counts[exam_id].append(_TypeCountRow(qtype, options))

    out = []
    for exam in exams:
        exam_questions = counts.get(exam.id, [])
        mcq, sata, fib, other = _question_type_counts(exam_questions)
        total = len(exam_questions)
        out.append(
            {
                "id": exam.id,
                "title": exam.title,
                "course_id": exam.course_id,
                "course_name": exam.course.name if exam.course else None,
                "time_limit_minutes": exam.time_limit_minutes,
                "total_questions": total,
                "mcq_count": mcq,
                "sata_count": sata,
                "fib_count": fib,
                "other_count": other,
                "created_at": exam.created_at.isoformat(),
            }
        )
    return out


@app.get("/api/exams/{exam_id}")
def get_exam(
    exam_id: str, user: CurrentUserDep, include_answers: bool = False, db: Session = Depends(get_db)
):
    # ponytail: include_answers is available to anyone who can see the exam, not
    # just the owner. take-exam.ts grades client-side for practice mode, so the
    # answer key is load-bearing for the student flow. Upgrade path: move reveal
    # and check-answer to server calls, then restrict this to the owner.
    exam = (
        db.query(Exam)
        .options(joinedload(Exam.course))
        .filter(Exam.id == exam_id, _visible(Exam, user))
        .first()
    )
    if not exam:
        raise HTTPException(404, "Exam not found")
    questions = []
    for q in exam.questions:
        qdict = {
            "id": q.id,
            "number": q.number,
            "topic": q.topic,
            "type": q.type,
            "question": q.question,
            "sections": q.sections,
            "options": q.options,
            "image": q.image,
        }
        if include_answers:
            qdict["answer"] = q.answer
            qdict["rationale"] = q.rationale or ""
        questions.append(qdict)
    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": exam.course.name if exam.course else None,
        "time_limit_minutes": exam.time_limit_minutes,
        "questions": questions,
    }


@app.patch("/api/exams/{exam_id}")
def update_exam_title(exam_id: str, payload: ExamTitleUpdate, user: CurrentUserDep, db: Session = Depends(get_db)):
    exam = get_owned_exam_or_404(exam_id, user, db)

    new_title = payload.title.strip()
    if not new_title:
        raise HTTPException(400, "Title cannot be empty")

    exam.title = new_title
    # The denormalized copies span every user who has taken this exam, which is
    # correct: the exam really was renamed. Ownership was already checked above.
    db.query(History).filter(History.exam_id == exam_id).update({"exam_title": new_title})
    db.query(InProgressExam).filter(InProgressExam.exam_id == exam_id).update({"exam_title": new_title})
    db.commit()
    db.refresh(exam)

    return _exam_summary(exam, db)


def _exam_summary(exam: Exam, db: Session) -> dict:
    qs = [
        _TypeCountRow(qtype, options)
        for qtype, options in db.query(Question.type, Question.options).filter(
            Question.exam_id == exam.id
        )
    ]
    mcq, sata, fib, other = _question_type_counts(qs)
    course = exam.course if exam.course_id else None
    if not course and exam.course_id:
        course = db.query(Course).filter(Course.id == exam.course_id).first()
    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": course.name if course else None,
        "time_limit_minutes": exam.time_limit_minutes,
        "total_questions": len(qs),
        "mcq_count": mcq,
        "sata_count": sata,
        "fib_count": fib,
        "other_count": other,
        "created_at": exam.created_at.isoformat(),
    }


@app.patch("/api/exams/{exam_id}/time-limit")
def update_exam_time_limit(exam_id: str, payload: ExamTimeLimitUpdate, user: CurrentUserDep, db: Session = Depends(get_db)):
    exam = get_owned_exam_or_404(exam_id, user, db)
    limit = payload.time_limit_minutes
    if limit is not None and limit <= 0:
        limit = None
    exam.time_limit_minutes = limit
    db.commit()
    db.refresh(exam)
    return _exam_summary(exam, db)


# ── Question CRUD (exam editor) ───────────────────────────────────

def _question_to_dict(q: Question) -> dict:
    return {
        "id": q.id,
        "number": q.number,
        "topic": q.topic,
        "type": q.type,
        "question": q.question,
        "sections": q.sections,
        "options": q.options,
        "answer": q.answer,
        "rationale": q.rationale or "",
        "image": q.image,
    }


@app.post("/api/exams/{exam_id}/questions")
def add_question(exam_id: str, payload: QuestionIn, user: CurrentUserDep, db: Session = Depends(get_db)):
    exam = get_owned_exam_or_404(exam_id, user, db)
    number = payload.number
    if not number or number <= 0:
        max_num = max((q.number for q in exam.questions), default=0)
        number = max_num + 1
    q = Question(
        exam_id=exam_id,
        number=number,
        topic=payload.topic,
        type=payload.type,
        question=payload.question,
        sections=payload.sections,
        options=payload.options,
        answer=payload.answer,
        rationale=payload.rationale,
        image=payload.image,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_to_dict(q)


@app.patch("/api/exams/{exam_id}/questions/{question_id}")
def update_question(exam_id: str, question_id: int, payload: QuestionUpdate, user: CurrentUserDep, db: Session = Depends(get_db)):
    get_owned_exam_or_404(exam_id, user, db)
    q = db.query(Question).filter(Question.id == question_id, Question.exam_id == exam_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    fields = payload.model_fields_set
    if "number" in fields and payload.number is not None:
        q.number = payload.number
    if "topic" in fields and payload.topic is not None:
        q.topic = payload.topic
    if "type" in fields and payload.type is not None:
        q.type = payload.type
    if "question" in fields and payload.question is not None:
        q.question = payload.question
    if "sections" in fields:
        q.sections = payload.sections
    if "options" in fields:
        q.options = payload.options
    if "answer" in fields:
        q.answer = payload.answer
    if "rationale" in fields and payload.rationale is not None:
        q.rationale = payload.rationale
    db.commit()
    db.refresh(q)
    return _question_to_dict(q)


@app.delete("/api/exams/{exam_id}/questions/{question_id}")
def delete_question(exam_id: str, question_id: int, user: CurrentUserDep, db: Session = Depends(get_db)):
    get_owned_exam_or_404(exam_id, user, db)
    q = db.query(Question).filter(Question.id == question_id, Question.exam_id == exam_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    _remove_image_file(q.image)
    db.delete(q)
    db.commit()
    return {"deleted": True}


# .svg is deliberately absent: SVGs are served from the same origin as the app,
# so a script inside one is stored XSS.
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _remove_image_file(image_url: str | None) -> None:
    if not image_url:
        return
    filename = image_url.rsplit("/", 1)[-1]
    path = UPLOADS_ROOT / filename
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def _get_owned_question_or_404(question_id: int, user: User, db: Session) -> Question:
    """question_id is a serial integer and trivially enumerable — these two routes
    take no exam_id, so ownership must be resolved by joining through Exam."""
    q = (
        db.query(Question)
        .join(Exam, Question.exam_id == Exam.id)
        .filter(Question.id == question_id, Exam.owner_id == user.id)
        .first()
    )
    if not q:
        raise HTTPException(404, "Question not found")
    return q


@app.post("/api/questions/{question_id}/image")
def upload_question_image(question_id: int, user: CurrentUserDep, file: UploadFile = File(...), db: Session = Depends(get_db)):
    q = _get_owned_question_or_404(question_id, user, db)
    ext = pathlib.Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported image type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}")

    filename = f"q{question_id}_{uuid4().hex[:10]}{ext}"
    dest = UPLOADS_ROOT / filename

    # Stream in bounded chunks rather than reading the whole upload into memory,
    # and only discard the previous image once the new one is safely on disk.
    written = 0
    try:
        with dest.open("wb") as out:
            while chunk := file.file.read(64 * 1024):
                written += len(chunk)
                if written > MAX_IMAGE_BYTES:
                    raise HTTPException(413, f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit")
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    previous = q.image
    q.image = f"/api/uploads/{filename}"
    db.commit()
    db.refresh(q)
    _remove_image_file(previous)
    return {"image": q.image}


@app.delete("/api/questions/{question_id}/image")
def delete_question_image(question_id: int, user: CurrentUserDep, db: Session = Depends(get_db)):
    q = _get_owned_question_or_404(question_id, user, db)
    _remove_image_file(q.image)
    q.image = None
    db.commit()
    return {"image": None}


@app.post("/api/exams/{exam_id}/submit")
def submit_exam(exam_id: str, submission: ExamSubmission, user: CurrentUserDep, db: Session = Depends(get_db)):
    exam = get_visible_exam_or_404(exam_id, user, db, with_questions=True)

    answer_map = {a.question_number: a.answer for a in submission.answers}
    fib_mark_map = {a.question_number: a.fib_correct for a in submission.answers if a.fib_correct is not None}
    results = []
    correct_count = 0

    selected_questions = exam.questions
    if submission.question_numbers:
        selected_set = set(submission.question_numbers)
        selected_questions = [q for q in exam.questions if q.number in selected_set]
        if not selected_questions:
            raise HTTPException(400, "No valid questions selected")

    for q in selected_questions:
        user_answer = answer_map.get(q.number)

        if _is_fib_question(q) and q.number in fib_mark_map:
            is_correct = fib_mark_map[q.number]
        else:
            is_correct = _grade_question(q, user_answer)

        if is_correct:
            correct_count += 1

        results.append({
            "question_number": q.number,
            "question": q.question,
            "topic": q.topic,
            "type": q.type,
            "sections": q.sections,
            "options": q.options,
            "image": q.image,
            "user_answer": user_answer,
            "correct_answer": q.answer,
            "is_correct": is_correct,
            "rationale": q.rationale or "",
        })

    total = len(selected_questions)
    score = correct_count / total if total else 0
    passed = score >= PASS_THRESHOLD

    record = History(
        id=str(uuid4())[:8],
        user_id=user.id,
        exam_id=exam_id,
        exam_title=exam.title,
        score=round(score * 100, 1),
        correct=correct_count,
        total=total,
        passed=passed,
        time_spent_seconds=submission.time_spent_seconds,
        results=results,
        mode=submission.mode,
        taken_at=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return _history_to_dict(record)


# ── In-Progress Endpoints ─────────────────────────────────────────

@app.post("/api/in-progress")
def save_progress(payload: SaveProgressPayload, user: CurrentUserDep, db: Session = Depends(get_db)):
    exam = get_visible_exam_or_404(payload.exam_id, user, db)

    now = datetime.now()
    # Autosave fires on a 500 ms debounce and two tabs will collide, so this is a
    # real race, not a theoretical one. UNIQUE(user_id, exam_id, mode) plus an
    # upsert replaces the old read-then-insert.
    stmt = pg_insert(InProgressExam.__table__).values(
        id=str(uuid4())[:8],
        user_id=user.id,
        exam_id=payload.exam_id,
        exam_title=exam.title,
        mode=payload.mode,
        answers=payload.answers,
        flagged=payload.flagged,
        question_order=payload.question_order,
        remaining_seconds=payload.remaining_seconds,
        current_page=payload.current_page,
        total_questions=len(payload.question_order),
        answered_count=len(payload.answers),
        started_at=now,
        saved_at=now,
    )
    # id and started_at are deliberately absent: rewriting id would break the live
    # resume link, and rewriting started_at would reset the dashboard's elapsed
    # timer on every autosave.
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "exam_id", "mode"],
        set_={
            "exam_title": stmt.excluded.exam_title,
            "answers": stmt.excluded.answers,
            "flagged": stmt.excluded.flagged,
            "question_order": stmt.excluded.question_order,
            "remaining_seconds": stmt.excluded.remaining_seconds,
            "current_page": stmt.excluded.current_page,
            "total_questions": stmt.excluded.total_questions,
            "answered_count": stmt.excluded.answered_count,
            "saved_at": stmt.excluded.saved_at,
        },
    )
    db.execute(stmt)
    db.commit()

    record = (
        db.query(InProgressExam)
        .filter(
            InProgressExam.user_id == user.id,
            InProgressExam.exam_id == payload.exam_id,
            InProgressExam.mode == payload.mode,
        )
        .first()
    )
    return _in_progress_to_dict(record)


@app.get("/api/in-progress")
def list_in_progress(user: CurrentUserDep, db: Session = Depends(get_db)):
    rows = (
        db.query(InProgressExam)
        .filter(InProgressExam.user_id == user.id)
        .order_by(InProgressExam.saved_at.desc())
        .all()
    )
    return [_in_progress_to_dict(r) for r in rows]


@app.get("/api/in-progress/{record_id}")
def get_in_progress(record_id: str, user: CurrentUserDep, db: Session = Depends(get_db)):
    record = (
        db.query(InProgressExam)
        .filter(InProgressExam.id == record_id, InProgressExam.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(404, "Record not found")
    return _in_progress_to_dict(record)


@app.delete("/api/in-progress/by-exam/{exam_id}")
def delete_in_progress_by_exam(exam_id: str, user: CurrentUserDep, mode: str = "exam", db: Session = Depends(get_db)):
    record = (
        db.query(InProgressExam)
        .filter(
            InProgressExam.exam_id == exam_id,
            InProgressExam.mode == mode,
            InProgressExam.user_id == user.id,
        )
        .first()
    )
    if record:
        db.delete(record)
        db.commit()
    return {"deleted": True}


@app.delete("/api/in-progress/{record_id}")
def delete_in_progress(record_id: str, user: CurrentUserDep, db: Session = Depends(get_db)):
    record = (
        db.query(InProgressExam)
        .filter(InProgressExam.id == record_id, InProgressExam.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(404, "Record not found")
    db.delete(record)
    db.commit()
    return {"deleted": True}


def _in_progress_to_dict(record: InProgressExam) -> dict:
    return {
        "id": record.id,
        "exam_id": record.exam_id,
        "exam_title": record.exam_title,
        "mode": record.mode,
        "answers": record.answers,
        "flagged": record.flagged,
        "question_order": record.question_order,
        "remaining_seconds": record.remaining_seconds,
        "current_page": record.current_page,
        "total_questions": record.total_questions,
        "answered_count": record.answered_count,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "saved_at": record.saved_at.isoformat(),
    }


# ── Admin Dashboard ───────────────────────────────────────────────

@app.get("/api/admin/dashboard")
def admin_dashboard(user: InstructorDep, limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    """Live view of every student's in-progress attempt. Instructors only."""
    rows = (
        db.query(InProgressExam)
        .options(joinedload(InProgressExam.user))
        .order_by(InProgressExam.saved_at.desc())
        .limit(limit)
        .all()
    )

    # One query for every exam on the page instead of one per row.
    exam_ids = {r.exam_id for r in rows}
    questions_by_exam: dict[str, dict[int, Question]] = {eid: {} for eid in exam_ids}
    if exam_ids:
        for q in db.query(Question).filter(Question.exam_id.in_(exam_ids)).all():
            questions_by_exam[q.exam_id][q.number] = q

    now = datetime.now()
    out = []
    for r in rows:
        seconds_since_last_answer = int((now - r.saved_at).total_seconds()) if r.saved_at else 0
        seconds_since_start = int((now - r.started_at).total_seconds()) if r.started_at else None

        correct_count = 0
        wrong_count = 0
        q_map = questions_by_exam.get(r.exam_id, {})
        for qnum_str, user_answer in (r.answers or {}).items():
            # Answer keys come from the client; a non-numeric key must not wedge
            # this endpoint for everyone.
            try:
                q = q_map.get(int(qnum_str))
            except (TypeError, ValueError):
                continue
            if not q:
                continue
            is_correct = _grade_question(q, user_answer)

            if is_correct:
                correct_count += 1
            else:
                wrong_count += 1

        answered = correct_count + wrong_count
        score_percent = round((correct_count / answered) * 100, 1) if answered > 0 else 0

        out.append({
            "id": r.id,
            "exam_id": r.exam_id,
            "exam_title": r.exam_title,
            "student_email": r.user.email if r.user else None,
            "mode": r.mode,
            "total_questions": r.total_questions,
            "answered_count": r.answered_count,
            "remaining_count": r.total_questions - r.answered_count,
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "score_percent": score_percent,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "saved_at": r.saved_at.isoformat(),
            "seconds_since_last_answer": seconds_since_last_answer,
            "seconds_since_start": seconds_since_start,
            "remaining_seconds": r.remaining_seconds,
        })
    return out


# ── History Endpoints ─────────────────────────────────────────────

@app.get("/api/history")
def get_history(user: CurrentUserDep, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    # Summaries only. `results` holds a full copy of every question, so returning
    # it for the whole list is a 100 MB+ response on a busy account.
    rows = (
        db.query(History)
        .filter(History.user_id == user.id)
        .order_by(History.taken_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [_history_summary(r) for r in rows]


@app.get("/api/history/topic-stats")
def get_history_topic_stats(user: CurrentUserDep, db: Session = Depends(get_db)):
    """Per-topic correct/total across all of this user's attempts.

    Aggregated in Postgres rather than by shipping every `results` blob to the
    browser — this is the only thing the overview page needed them for.
    """
    rows = db.execute(
        text(
            """
            SELECT COALESCE(elem->>'topic', '') AS topic,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE (elem->>'is_correct')::boolean) AS correct
            FROM history, LATERAL jsonb_array_elements(history.results) AS elem
            WHERE history.user_id = :user_id
            GROUP BY 1
            """
        ),
        {"user_id": user.id},
    ).all()

    stats = [
        {
            "topic": topic,
            "total": total,
            "correct": correct,
            "score": round((correct / total) * 100) if total else 0,
        }
        for topic, total, correct in rows
    ]
    stats.sort(key=lambda s: s["score"], reverse=True)
    return stats


@app.get("/api/history/{record_id}")
def get_history_record(record_id: str, user: CurrentUserDep, db: Session = Depends(get_db)):
    record = db.query(History).filter(History.id == record_id, History.user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found")
    return _history_to_dict(record)


@app.delete("/api/history/{record_id}")
def delete_history_record(record_id: str, user: CurrentUserDep, db: Session = Depends(get_db)):
    record = db.query(History).filter(History.id == record_id, History.user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found")
    db.delete(record)
    db.commit()
    return {"deleted": True}


@app.delete("/api/exams/{exam_id}")
def delete_exam(exam_id: str, user: CurrentUserDep, db: Session = Depends(get_db)):
    exam = get_owned_exam_or_404(exam_id, user, db)
    # Questions cascade, but their image files do not — reclaim them first.
    for q in db.query(Question).filter(Question.exam_id == exam_id).all():
        _remove_image_file(q.image)
    db.delete(exam)
    db.commit()
    return {"deleted": True}


def _history_summary(record: History) -> dict:
    """Everything the history list renders, minus the heavy `results` blob."""
    return {
        "id": record.id,
        "exam_id": record.exam_id,
        "exam_title": record.exam_title,
        "score": record.score,
        "correct": record.correct,
        "total": record.total,
        "passed": record.passed,
        "time_spent_seconds": record.time_spent_seconds,
        "mode": record.mode or "exam",
        "taken_at": record.taken_at.isoformat(),
    }


def _history_to_dict(record: History) -> dict:
    return {**_history_summary(record), "results": record.results}
