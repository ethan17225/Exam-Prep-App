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
    db = SessionLocal()

    try:
        existing = db.query(Exam).count()
        if existing:
            print(f"Database already has {existing} exam(s) — skipping seed.")
            return

        data = json.loads(SEED_FILE.read_text(encoding="utf-8"))

        for key in sorted(data.keys()):
            exam_number = key.replace("exam", "")
            exam_id = str(uuid4())[:8]
            exam = Exam(
                id=exam_id,
                title=f"Exam {exam_number}",
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
