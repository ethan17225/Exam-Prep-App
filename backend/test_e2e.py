#!/usr/bin/env python3
"""End-to-end smoke test for question types (run against a live backend)."""

import json
import sys
import urllib.request

BASE = "http://localhost:8001/api"

TEST_EXAM = {
    "title": "__e2e_smoke_test__",
    "questions": [
        {
            "number": 1,
            "topic": "Matrix",
            "type": "MATRIX",
            "question": "Match each finding.",
            "options": {"rows": ["HgA1C 6.8%"], "columns": ["Type 1 Diabetes", "Type 2 Diabetes"]},
            "answer": {"0": ["Type 1 Diabetes", "Type 2 Diabetes"]},
            "rationale": "",
        },
        {
            "number": 2,
            "topic": "Cloze",
            "type": "CLOZE",
            "question": "The client should [1] and [2].",
            "options": {
                "blanks": [
                    {"label": "1", "choices": ["fast", "drink orange juice"]},
                    {"label": "2", "choices": ["monitor", "call 911"]},
                ]
            },
            "answer": ["drink orange juice", "monitor"],
            "rationale": "",
        },
        {
            "number": 3,
            "topic": "Bowtie",
            "type": "BOWTIE",
            "question": "Select condition and interventions.",
            "options": {
                "categories": [
                    {"name": "Potential Condition", "count": 1, "choices": ["Acrocyanosis", "Meconium aspiration syndrome"]},
                    {"name": "Potential Interventions", "count": 2, "choices": ["Suctioning", "Oxygen therapy", "Phototherapy"]},
                ]
            },
            "answer": {
                "Potential Condition": ["Meconium aspiration syndrome"],
                "Potential Interventions": ["Suctioning", "Oxygen therapy"],
            },
            "rationale": "",
        },
        {
            "number": 4,
            "topic": "Ranking",
            "type": "RANKING",
            "question": "Rank from highest to lowest risk.",
            "options": ["Older males", "Older females"],
            "answer": ["Older females", "Older males"],
            "rationale": "",
        },
        {
            "number": 5,
            "topic": "Highlight",
            "type": "HIGHLIGHT",
            "question": "Highlight findings that need follow-up.",
            "options": {"tokens": ["BP 160/100", "HR 88", "BMI 35.9"]},
            "answer": [0, 2],
            "rationale": "",
        },
        {
            "number": 6,
            "topic": "Hotspot",
            "type": "HOTSPOT",
            "question": "Click the correct region.",
            "options": {"regions": [{"id": "r1", "label": "Up", "x": 55, "y": 5, "w": 40, "h": 30}, {"id": "r2", "label": "Down", "x": 55, "y": 60, "w": 40, "h": 30}]},
            "answer": "r2",
            "rationale": "",
        },
        {"number": 7, "topic": "MCQ", "type": "MCQ", "question": "Pick one.", "options": ["A. one", "B. two"], "answer": "A", "rationale": ""},
        {"number": 8, "topic": "SATA", "type": "SATA", "question": "Pick all.", "options": ["A. one", "B. two", "C. three"], "answer": ["A", "C"], "rationale": ""},
        {"number": 9, "topic": "FIB", "type": "FIB", "question": "Enter value.", "answer": "42", "rationale": ""},
    ],
}


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.load(r)


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def patch(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def delete(path):
    req = urllib.request.Request(BASE + path, method="DELETE")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def upload_image(question_id, filename, content):
    boundary = "----testboundary123"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/questions/{question_id}/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# ── Create a temporary exam for testing ─────────────────────────
courses = get("/courses")
course_id = courses[0]["id"] if courses else None
created = post("/exams", {**TEST_EXAM, "course_id": course_id})
exam_id = created["exam_id"]
check("test exam created", created["total_questions"] == len(TEST_EXAM["questions"]))

detail = get(f"/exams/{exam_id}?include_answers=true")
questions = detail["questions"]
check("questions include id and image fields", all("id" in q and "image" in q for q in questions))

# ── Submit all-correct answers ──────────────────────────────────
subs = [{"question_number": q["number"], "answer": q["answer"], "fib_correct": None} for q in questions]
result = post(f"/exams/{exam_id}/submit", {
    "exam_id": exam_id,
    "answers": subs,
    "time_spent_seconds": 60,
    "mode": "practice",
})
check(
    "all-correct submission scores 100%",
    result["score"] == 100.0,
    f"score={result['score']}, wrong={[r['question_number'] for r in result['results'] if not r['is_correct']]}",
)
delete(f"/history/{result['id']}")

# ── Submit with wrong answers ───────────────────────────────────
wrong_by_type = {
    "MATRIX": {"0": ["Type 1 Diabetes"]},
    "CLOZE": [],
    "BOWTIE": {"Potential Condition": ["Acrocyanosis"]},
    "RANKING": ["a", "b"],
    "HIGHLIGHT": [1],
    "HOTSPOT": "nope",
    "MCQ": "Z",
    "SATA": ["Z"],
    "FIB": "999999",
}
subs2 = [
    {"question_number": q["number"], "answer": wrong_by_type.get(q["type"].upper(), ""), "fib_correct": None}
    for q in questions
]
result2 = post(f"/exams/{exam_id}/submit", {
    "exam_id": exam_id,
    "answers": subs2,
    "time_spent_seconds": 60,
    "mode": "practice",
})
check("all-wrong submission scores 0%", result2["score"] == 0.0, f"score={result2['score']}")
delete(f"/history/{result2['id']}")

# ── Question CRUD ───────────────────────────────────────────────
q7 = next(q for q in questions if q["number"] == 7)
updated = patch(f"/exams/{exam_id}/questions/{q7['id']}", {"topic": "Updated"})
check("question PATCH works", updated["topic"] == "Updated")
patch(f"/exams/{exam_id}/questions/{q7['id']}", {"topic": "MCQ"})

new_q = post(f"/exams/{exam_id}/questions", {
    "number": 0,
    "topic": "Test",
    "type": "MCQ",
    "question": "Temp question?",
    "options": ["A. one", "B. two"],
    "answer": "A",
    "rationale": "",
})
check("question POST assigns next number", new_q["number"] == 10, str(new_q["number"]))

# ── Image upload ────────────────────────────────────────────────
png = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f0300050001a5f645400000000049454e44ae426082"
)
img = upload_image(new_q["id"], "test.png", png)
check("image upload returns URL", img["image"].startswith("/api/uploads/"), str(img))

with urllib.request.urlopen("http://localhost:8001" + img["image"]) as r:
    served = r.read()
check("uploaded image is served", served == png)

deleted_img = delete(f"/questions/{new_q['id']}/image")
check("image delete works", deleted_img["image"] is None)

deleted = delete(f"/exams/{exam_id}/questions/{new_q['id']}")
check("question DELETE works", deleted["deleted"] is True)

# ── Time limit route ────────────────────────────────────────────
tl = patch(f"/exams/{exam_id}/time-limit", {"time_limit_minutes": 45})
check("time-limit PATCH works", tl["time_limit_minutes"] == 45)
patch(f"/exams/{exam_id}/time-limit", {"time_limit_minutes": None})

# ── Cleanup test exam ───────────────────────────────────────────
delete(f"/exams/{exam_id}")
remaining = [e for e in get("/exams") if e["title"] == TEST_EXAM["title"]]
check("test exam deleted", len(remaining) == 0)

print()
if failures:
    print(f"{len(failures)} check(s) FAILED: {failures}")
    sys.exit(1)
print("All checks passed.")
