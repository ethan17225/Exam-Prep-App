#!/usr/bin/env python3
"""Replace exams in the DB from exam{N}.json files in this directory."""

import json
import pathlib
import re
import sys
from datetime import datetime
from uuid import uuid4

from database import Base, engine, SessionLocal
from models import Exam, Question

ROOT = pathlib.Path(__file__).resolve().parent
NAME_RE = re.compile(r"^exam(\d+)\.json$")


def _paths() -> list[pathlib.Path]:
    found: list[tuple[int, pathlib.Path]] = []
    for p in ROOT.glob("exam*.json"):
        m = NAME_RE.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    return [p for _, p in sorted(found)]


def import_file(path: pathlib.Path) -> bool:
    m = NAME_RE.match(path.name)
    assert m
    n = int(m.group(1))
    key = f"exam{n}"
    title = f"Exam {n}"

    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get(key)
    if not items:
        print(f"Skip {path.name}: missing or empty {key!r}", file=sys.stderr)
        return False

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(Exam).filter(Exam.title == title).first()
        if existing:
            db.delete(existing)
            db.commit()

        exam_id = str(uuid4())[:8]
        exam = Exam(id=exam_id, title=title, created_at=datetime.now())
        db.add(exam)

        for q in items:
            db.add(
                Question(
                    exam_id=exam_id,
                    number=q["number"],
                    topic=q.get("topic", ""),
                    type=q.get("type", "MCQ"),
                    question=q["question"],
                    options=q.get("options"),
                    answer=q["answer"],
                    rationale=q.get("rationale", ""),
                )
            )

        db.commit()
        print(f"Imported {title} → id {exam_id} ({len(items)} questions)")
        return True
    finally:
        db.close()


def main() -> None:
    if len(sys.argv) > 1:
        paths = []
        for a in sys.argv[1:]:
            try:
                n = int(a)
            except ValueError:
                print(f"Bad exam number: {a!r}", file=sys.stderr)
                sys.exit(1)
            p = ROOT / f"exam{n}.json"
            if not p.is_file():
                print(f"Missing {p}", file=sys.stderr)
                sys.exit(1)
            paths.append(p)
    else:
        paths = _paths()
        if not paths:
            print(f"No exam<N>.json files under {ROOT}", file=sys.stderr)
            sys.exit(1)
    ok = 0
    for path in paths:
        if import_file(path):
            ok += 1
    print(f"Done: {ok}/{len(paths)} file(s).")


if __name__ == "__main__":
    main()
