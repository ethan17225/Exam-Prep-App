# MCQ Exam App

A minimalist web app for taking MCQ, Select All That Apply (SATA), and Fill in the Blank (FIB) exams.

## Tech Stack

- **Frontend:** Angular 21
- **Backend:** FastAPI (Python) with in-memory storage

## Quick Start

### 1. Backend

```bash
cd backend
pip3 install -r requirements.txt
uvicorn main:app --port 8001 --reload
```

API runs at `http://localhost:8001`. Swagger docs at `http://localhost:8001/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npx ng serve
```

App runs at `http://localhost:4200`.

## Features

- **Upload** — Paste or upload a JSON file with exam questions
- **Exams** — Browse and start available exams
- **Timer** — Elapsed time clock during exam-taking
- **Question types** — MCQ (single choice), SATA (multi-select), FIB (text input)
- **Question navigator** — Jump to any question, flag questions for review
- **Results** — Detailed review with correct/incorrect highlighting and rationales
- **History** — View all past test attempts with scores
- **Pass threshold** — 75% required to pass

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
