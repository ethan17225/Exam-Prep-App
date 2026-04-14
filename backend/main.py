from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from uuid import uuid4
import pathlib
from sqlalchemy.orm import Session, joinedload

from sqlalchemy import text, inspect as sa_inspect

from database import Base, engine, get_db
from models import Course, Exam, Question, History, InProgressExam

Base.metadata.create_all(bind=engine)

with engine.connect() as _conn:
    _cols = [c["name"] for c in sa_inspect(engine).get_columns("history")]
    if "mode" not in _cols:
        _conn.execute(text("ALTER TABLE history ADD COLUMN mode VARCHAR(10) DEFAULT 'exam'"))
        _conn.commit()

    _ip_cols = [c["name"] for c in sa_inspect(engine).get_columns("in_progress_exams")]
    if "started_at" not in _ip_cols:
        _conn.execute(text("ALTER TABLE in_progress_exams ADD COLUMN started_at TIMESTAMP"))
        _conn.commit()

    # -- Course migration --
    _exam_cols = [c["name"] for c in sa_inspect(engine).get_columns("exams")]
    if "course_id" not in _exam_cols:
        _conn.execute(text("ALTER TABLE exams ADD COLUMN course_id VARCHAR(8) REFERENCES courses(id) ON DELETE SET NULL"))
        _conn.commit()

    # Ensure a default "Lab 4" course exists and backfill existing exams
    from database import SessionLocal as _SL
    _db = _SL()
    try:
        _default = _db.query(Course).filter(Course.name == "Lab 4").first()
        if not _default:
            _default = Course(id=str(uuid4())[:8], name="Lab 4", created_at=datetime.now())
            _db.add(_default)
            _db.commit()
            _db.refresh(_default)
        _db.query(Exam).filter(Exam.course_id.is_(None)).update({"course_id": _default.id})
        _db.commit()
    finally:
        _db.close()

app = FastAPI(title="MCQ Exam API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOCS_ROOT = pathlib.Path(__file__).resolve().parent / "Docs"
DOCS_ROOT.mkdir(exist_ok=True)

# Mount static file serving for the Docs folder (PDFs and HTML)
app.mount("/docs-files", StaticFiles(directory=str(DOCS_ROOT)), name="docs-files")

PASS_THRESHOLD = 0.72


def _question_type_counts(questions: list) -> tuple[int, int, int]:
    """Return (mcq, sata, fib) using the same rules as submit grading."""
    mcq = sata = fib = 0
    for q in questions:
        if q.type == "SATA":
            sata += 1
        elif q.type in ("FIB", "Fill-in-the-blank") or not q.options:
            fib += 1
        else:
            mcq += 1
    return mcq, sata, fib


# ── Pydantic schemas ─────────────────────────────────────────────

class QuestionIn(BaseModel):
    number: int
    topic: str
    type: str
    question: str
    options: list[str] | None = None
    answer: str | list[str]
    rationale: str = ""


class ExamCreate(BaseModel):
    title: str
    questions: list[QuestionIn]
    course_id: str | None = None


class ExamTitleUpdate(BaseModel):
    title: str


class AnswerSubmission(BaseModel):
    question_number: int
    answer: str | list[str]
    fib_correct: bool | None = None


class ExamSubmission(BaseModel):
    exam_id: str
    answers: list[AnswerSubmission]
    time_spent_seconds: int
    mode: str = "exam"
    question_numbers: list[int] | None = None


class SaveProgressPayload(BaseModel):
    exam_id: str
    mode: str = "exam"
    answers: dict[str, str | list[str]]
    flagged: list[int]
    question_order: list[int]
    remaining_seconds: int
    current_page: int = 0


# ── Course Endpoints ──────────────────────────────────────────────

class CourseCreate(BaseModel):
    name: str


@app.get("/api/courses")
def list_courses(db: Session = Depends(get_db)):
    courses = db.query(Course).order_by(Course.name).all()
    return [
        {"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()}
        for c in courses
    ]


@app.post("/api/courses")
def create_course(payload: CourseCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Course name cannot be empty")
    existing = db.query(Course).filter(Course.name == name).first()
    if existing:
        raise HTTPException(409, "A course with this name already exists")
    course = Course(id=str(uuid4())[:8], name=name, created_at=datetime.now())
    db.add(course)
    db.commit()
    db.refresh(course)
    return {"id": course.id, "name": course.name, "created_at": course.created_at.isoformat()}


# ── Document Endpoints ────────────────────────────────────────────

@app.get("/api/documents")
def list_documents(course_id: str | None = Query(None), db: Session = Depends(get_db)):
    """Scan Docs/<course>/pdf/ folders and return documents grouped by course."""
    courses = db.query(Course).all()
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
def get_document_html(path: str = Query(...)):
    """Read and return the raw HTML content of a document."""
    import urllib.parse

    decoded = urllib.parse.unquote(path)
    rel = decoded.removeprefix("/docs-files/").removeprefix("/")
    html_path = DOCS_ROOT / rel

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
def create_exam(payload: ExamCreate, db: Session = Depends(get_db)):
    exam_id = str(uuid4())[:8]
    exam = Exam(id=exam_id, title=payload.title, course_id=payload.course_id, created_at=datetime.now())
    db.add(exam)
    for q in payload.questions:
        db.add(Question(
            exam_id=exam_id,
            number=q.number,
            topic=q.topic,
            type=q.type,
            question=q.question,
            options=q.options,
            answer=q.answer,
            rationale=q.rationale,
        ))
    db.commit()
    return {"exam_id": exam_id, "total_questions": len(payload.questions)}


@app.get("/api/exams")
def list_exams(course_id: str | None = Query(None), db: Session = Depends(get_db)):
    query = db.query(Exam).options(joinedload(Exam.questions), joinedload(Exam.course))
    if course_id:
        query = query.filter(Exam.course_id == course_id)
    exams = query.order_by(Exam.created_at).all()
    out = []
    for exam in exams:
        mcq, sata, fib = _question_type_counts(exam.questions)
        total = len(exam.questions)
        out.append(
            {
                "id": exam.id,
                "title": exam.title,
                "course_id": exam.course_id,
                "course_name": exam.course.name if exam.course else None,
                "total_questions": total,
                "mcq_count": mcq,
                "sata_count": sata,
                "fib_count": fib,
                "created_at": exam.created_at.isoformat(),
            }
        )
    return out


@app.get("/api/exams/{exam_id}")
def get_exam(exam_id: str, include_answers: bool = False, db: Session = Depends(get_db)):
    exam = db.query(Exam).options(joinedload(Exam.course)).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")
    questions = []
    for q in exam.questions:
        qdict = {
            "number": q.number,
            "topic": q.topic,
            "type": q.type,
            "question": q.question,
            "options": q.options,
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
        "questions": questions,
    }


@app.patch("/api/exams/{exam_id}")
def update_exam_title(exam_id: str, payload: ExamTitleUpdate, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")

    new_title = payload.title.strip()
    if not new_title:
        raise HTTPException(400, "Title cannot be empty")

    exam.title = new_title
    db.query(History).filter(History.exam_id == exam_id).update({"exam_title": new_title})
    db.query(InProgressExam).filter(InProgressExam.exam_id == exam_id).update({"exam_title": new_title})
    db.commit()
    db.refresh(exam)

    qs = db.query(Question).filter(Question.exam_id == exam_id).all()
    mcq, sata, fib = _question_type_counts(qs)
    total_questions = len(qs)
    course = exam.course if exam.course_id else None
    if not course and exam.course_id:
        course = db.query(Course).filter(Course.id == exam.course_id).first()
    return {
        "id": exam.id,
        "title": exam.title,
        "course_id": exam.course_id,
        "course_name": course.name if course else None,
        "total_questions": total_questions,
        "mcq_count": mcq,
        "sata_count": sata,
        "fib_count": fib,
        "created_at": exam.created_at.isoformat(),
    }


@app.post("/api/exams/{exam_id}/submit")
def submit_exam(exam_id: str, submission: ExamSubmission, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")

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
        expected = q.answer

        is_fib = q.type in ("FIB", "Fill-in-the-blank") or not q.options

        if is_fib and q.number in fib_mark_map:
            is_correct = fib_mark_map[q.number]
        elif q.type == "SATA":
            if isinstance(expected, list):
                expected_set = set(e.strip() for e in expected)
            else:
                expected_set = set(e.strip() for e in str(expected).split(","))
            if isinstance(user_answer, list):
                user_set = set(u.strip() for u in user_answer)
            elif user_answer:
                user_set = set(u.strip() for u in str(user_answer).split(","))
            else:
                user_set = set()
            is_correct = expected_set == user_set
        elif is_fib:
            user_str = str(user_answer or "").strip().lower()
            expected_str = str(expected).strip().lower()
            try:
                is_correct = float(user_str) == float(expected_str)
            except (ValueError, TypeError):
                is_correct = (
                    user_str == expected_str
                    or (len(user_str) >= 3 and user_str in expected_str)
                    or (len(expected_str) >= 3 and expected_str in user_str)
                )
        else:
            is_correct = str(user_answer or "").strip() == str(expected).strip()

        if is_correct:
            correct_count += 1

        results.append({
            "question_number": q.number,
            "question": q.question,
            "topic": q.topic,
            "type": q.type,
            "options": q.options,
            "user_answer": user_answer,
            "correct_answer": expected,
            "is_correct": is_correct,
            "rationale": q.rationale or "",
        })

    total = len(selected_questions)
    score = correct_count / total if total else 0
    passed = score >= PASS_THRESHOLD

    record = History(
        id=str(uuid4())[:8],
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
def save_progress(payload: SaveProgressPayload, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == payload.exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")

    existing = (
        db.query(InProgressExam)
        .filter(InProgressExam.exam_id == payload.exam_id, InProgressExam.mode == payload.mode)
        .first()
    )

    if existing:
        existing.answers = payload.answers
        existing.flagged = payload.flagged
        existing.question_order = payload.question_order
        existing.remaining_seconds = payload.remaining_seconds
        existing.current_page = payload.current_page
        existing.total_questions = len(payload.question_order)
        existing.answered_count = len(payload.answers)
        existing.saved_at = datetime.now()
        db.commit()
        db.refresh(existing)
        return _in_progress_to_dict(existing)

    now = datetime.now()
    total = len(payload.question_order)
    record = InProgressExam(
        id=str(uuid4())[:8],
        exam_id=payload.exam_id,
        exam_title=exam.title,
        mode=payload.mode,
        answers=payload.answers,
        flagged=payload.flagged,
        question_order=payload.question_order,
        remaining_seconds=payload.remaining_seconds,
        current_page=payload.current_page,
        total_questions=total,
        answered_count=len(payload.answers),
        started_at=now,
        saved_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _in_progress_to_dict(record)


@app.get("/api/in-progress")
def list_in_progress(db: Session = Depends(get_db)):
    rows = db.query(InProgressExam).order_by(InProgressExam.saved_at.desc()).all()
    return [_in_progress_to_dict(r) for r in rows]


@app.get("/api/in-progress/{record_id}")
def get_in_progress(record_id: str, db: Session = Depends(get_db)):
    record = db.query(InProgressExam).filter(InProgressExam.id == record_id).first()
    if not record:
        raise HTTPException(404, "Record not found")
    return _in_progress_to_dict(record)


@app.delete("/api/in-progress/by-exam/{exam_id}")
def delete_in_progress_by_exam(exam_id: str, mode: str = "exam", db: Session = Depends(get_db)):
    record = (
        db.query(InProgressExam)
        .filter(InProgressExam.exam_id == exam_id, InProgressExam.mode == mode)
        .first()
    )
    if record:
        db.delete(record)
        db.commit()
    return {"deleted": True}


@app.delete("/api/in-progress/{record_id}")
def delete_in_progress(record_id: str, db: Session = Depends(get_db)):
    record = db.query(InProgressExam).filter(InProgressExam.id == record_id).first()
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
def admin_dashboard(db: Session = Depends(get_db)):
    rows = db.query(InProgressExam).order_by(InProgressExam.saved_at.desc()).all()
    now = datetime.now()
    out = []
    for r in rows:
        seconds_since_last_answer = int((now - r.saved_at).total_seconds()) if r.saved_at else 0
        seconds_since_start = int((now - r.started_at).total_seconds()) if r.started_at else None

        correct_count = 0
        wrong_count = 0
        questions = db.query(Question).filter(Question.exam_id == r.exam_id).all()
        q_map = {q.number: q for q in questions}
        for qnum_str, user_answer in (r.answers or {}).items():
            q = q_map.get(int(qnum_str))
            if not q:
                continue
            expected = q.answer
            is_fib = q.type in ("FIB", "Fill-in-the-blank") or not q.options
            if q.type == "SATA":
                if isinstance(expected, list):
                    expected_set = set(e.strip() for e in expected)
                else:
                    expected_set = set(e.strip() for e in str(expected).split(","))
                if isinstance(user_answer, list):
                    user_set = set(u.strip() for u in user_answer)
                elif user_answer:
                    user_set = set(u.strip() for u in str(user_answer).split(","))
                else:
                    user_set = set()
                is_correct = expected_set == user_set
            elif is_fib:
                user_str = str(user_answer or "").strip().lower()
                expected_str = str(expected).strip().lower()
                try:
                    is_correct = float(user_str) == float(expected_str)
                except (ValueError, TypeError):
                    is_correct = (
                        user_str == expected_str
                        or (len(user_str) >= 3 and user_str in expected_str)
                        or (len(expected_str) >= 3 and expected_str in user_str)
                    )
            else:
                is_correct = str(user_answer or "").strip() == str(expected).strip()

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
def get_history(db: Session = Depends(get_db)):
    rows = db.query(History).order_by(History.taken_at.desc()).all()
    return [_history_to_dict(r) for r in rows]


@app.get("/api/history/{record_id}")
def get_history_record(record_id: str, db: Session = Depends(get_db)):
    record = db.query(History).filter(History.id == record_id).first()
    if not record:
        raise HTTPException(404, "Record not found")
    return _history_to_dict(record)


@app.delete("/api/history/{record_id}")
def delete_history_record(record_id: str, db: Session = Depends(get_db)):
    record = db.query(History).filter(History.id == record_id).first()
    if not record:
        raise HTTPException(404, "Record not found")
    db.delete(record)
    db.commit()
    return {"deleted": True}


@app.delete("/api/exams/{exam_id}")
def delete_exam(exam_id: str, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")
    db.delete(exam)
    db.commit()
    return {"deleted": True}


def _history_to_dict(record: History) -> dict:
    return {
        "id": record.id,
        "exam_id": record.exam_id,
        "exam_title": record.exam_title,
        "score": record.score,
        "correct": record.correct,
        "total": record.total,
        "passed": record.passed,
        "time_spent_seconds": record.time_spent_seconds,
        "results": record.results,
        "mode": record.mode or "exam",
        "taken_at": record.taken_at.isoformat(),
    }
