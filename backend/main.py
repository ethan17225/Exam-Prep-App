from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import func

from sqlalchemy import text, inspect as sa_inspect

from database import Base, engine, get_db
from models import Exam, Question, History

Base.metadata.create_all(bind=engine)

with engine.connect() as _conn:
    _cols = [c["name"] for c in sa_inspect(engine).get_columns("history")]
    if "mode" not in _cols:
        _conn.execute(text("ALTER TABLE history ADD COLUMN mode VARCHAR(10) DEFAULT 'exam'"))
        _conn.commit()

app = FastAPI(title="MCQ Exam API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PASS_THRESHOLD = 0.75


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


class AnswerSubmission(BaseModel):
    question_number: int
    answer: str | list[str]


class ExamSubmission(BaseModel):
    exam_id: str
    answers: list[AnswerSubmission]
    time_spent_seconds: int
    mode: str = "exam"


# ── Endpoints ─────────────────────────────────────────────────────

@app.post("/api/exams")
def create_exam(payload: ExamCreate, db: Session = Depends(get_db)):
    exam_id = str(uuid4())[:8]
    exam = Exam(id=exam_id, title=payload.title, created_at=datetime.now())
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
def list_exams(db: Session = Depends(get_db)):
    rows = (
        db.query(Exam.id, Exam.title, Exam.created_at, func.count(Question.id).label("total_questions"))
        .outerjoin(Question)
        .group_by(Exam.id)
        .order_by(Exam.created_at)
        .all()
    )
    return [
        {
            "id": r.id,
            "title": r.title,
            "total_questions": r.total_questions,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.get("/api/exams/{exam_id}")
def get_exam(exam_id: str, include_answers: bool = False, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
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
    return {"id": exam.id, "title": exam.title, "questions": questions}


@app.post("/api/exams/{exam_id}/submit")
def submit_exam(exam_id: str, submission: ExamSubmission, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")

    answer_map = {a.question_number: a.answer for a in submission.answers}
    results = []
    correct_count = 0

    for q in exam.questions:
        user_answer = answer_map.get(q.number)
        expected = q.answer

        if q.type == "SATA":
            expected_set = set(expected) if isinstance(expected, list) else {expected}
            user_set = set(user_answer) if isinstance(user_answer, list) else ({user_answer} if user_answer else set())
            is_correct = expected_set == user_set
        elif q.type == "FIB":
            is_correct = str(user_answer or "").strip().lower() == str(expected).strip().lower()
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

    total = len(exam.questions)
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
