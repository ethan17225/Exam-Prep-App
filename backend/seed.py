#!/usr/bin/env python3
"""Seed the PostgreSQL database with questions from seed_data.json."""

import json
import pathlib
import re
import sys
from datetime import datetime
from uuid import uuid4

from database import Base, engine, SessionLocal
from models import Exam, Question

SEED_FILE = pathlib.Path(__file__).with_name("seed_data.json")


def _exam_sort_key(exam: Exam) -> tuple[int, str]:
    m = re.match(r"^\s*Exam\s+(\d+)\s*$", exam.title, re.I)
    if m:
        return (int(m.group(1)), exam.title)
    return (10**9, exam.title)


def export_seed(path: pathlib.Path | None = None) -> None:
    """Write exams and questions from the database to a JSON seed file."""
    path = path or SEED_FILE
    Base.metadata.create_all(bind=engine)

    from sqlalchemy import text, inspect as sa_inspect
    with engine.connect() as conn:
        exam_cols = [c["name"] for c in sa_inspect(engine).get_columns("exams")]
        if "course_id" not in exam_cols:
            conn.execute(text(
                "ALTER TABLE exams ADD COLUMN course_id VARCHAR(8) REFERENCES courses(id) ON DELETE SET NULL"
            ))
            conn.commit()

    db = SessionLocal()
    try:
        exams = sorted(db.query(Exam).all(), key=_exam_sort_key)
        out: dict[str, list[dict]] = {}
        for e in exams:
            m = re.match(r"^\s*Exam\s+(\d+)\s*$", e.title, re.I)
            key = f"exam{m.group(1)}" if m else f"exam_{e.id}"
            qs = sorted(e.questions, key=lambda q: q.number)
            items = []
            for q in qs:
                item: dict = {
                    "number": q.number,
                    "topic": q.topic or "",
                    "type": q.type or "MCQ",
                    "question": q.question,
                    "answer": q.answer,
                    "rationale": q.rationale or "",
                }
                if q.options is not None:
                    item["options"] = q.options
                items.append(item)
            out[key] = items

        path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(out)} exam(s) to {path}")
    finally:
        db.close()


def seed():
    Base.metadata.create_all(bind=engine)

    # Ensure course_id column exists on the exams table (may run before main.py migration)
    from sqlalchemy import text, inspect as sa_inspect
    from models import Course

    with engine.connect() as conn:
        exam_cols = [c["name"] for c in sa_inspect(engine).get_columns("exams")]
        if "course_id" not in exam_cols:
            conn.execute(text(
                "ALTER TABLE exams ADD COLUMN course_id VARCHAR(8) REFERENCES courses(id) ON DELETE SET NULL"
            ))
            conn.commit()

    db = SessionLocal()

    try:
        # Ensure default course exists
        default_course = db.query(Course).filter(Course.name == "Lab 4").first()
        if not default_course:
            default_course = Course(id=str(uuid4())[:8], name="Lab 4", created_at=datetime.now())
            db.add(default_course)
            db.commit()
            db.refresh(default_course)

        existing = db.query(Exam).count()
        if existing:
            print(f"Database already has {existing} exam(s) — skipping seed.")
            return

        data = json.loads(SEED_FILE.read_text(encoding="utf-8"))

        def _seed_key_order(k: str) -> tuple[int, str]:
            m = re.fullmatch(r"exam(\d+)", k)
            if m:
                return (int(m.group(1)), k)
            return (10**9, k)

        for key in sorted(data.keys(), key=_seed_key_order):
            exam_number = key.replace("exam", "")
            exam_id = str(uuid4())[:8]
            exam = Exam(
                id=exam_id,
                title=f"Exam {exam_number}",
                course_id=default_course.id,
                created_at=datetime.now(),
            )
            db.add(exam)

            for q in data[key]:
                db.add(Question(
                    exam_id=exam_id,
                    number=q["number"],
                    topic=q.get("topic", ""),
                    type=q.get("type", "MCQ"),
                    question=q["question"],
                    options=q.get("options"),
                    answer=q["answer"],
                    rationale=q.get("rationale", ""),
                ))

        db.commit()
        print(f"Seeded {len(data)} exams with {sum(len(v) for v in data.values())} questions.")

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("export", "dump"):
        export_seed()
    else:
        seed()
