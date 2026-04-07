#!/usr/bin/env python3
"""Seed the PostgreSQL database with questions from seed_data.json."""

import json
import pathlib
from datetime import datetime
from uuid import uuid4

from database import Base, engine, SessionLocal
from models import Exam, Question

SEED_FILE = pathlib.Path(__file__).with_name("seed_data.json")


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
    seed()
