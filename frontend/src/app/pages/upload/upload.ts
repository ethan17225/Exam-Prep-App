import { Component, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService } from '../../services/exam.service';

@Component({
  selector: 'app-upload',
  imports: [FormsModule],
  templateUrl: './upload.html',
  styleUrl: './upload.scss',
})
export class UploadPage {
  title = signal('');
  jsonText = signal('');
  error = signal('');
  loading = signal(false);
  showExample = signal(false);
  copied = signal(false);

  private readonly exampleJson = `[
  {
    "number": 1,
    "topic": "Pharmacology",
    "type": "MCQ",
    "question": "Which medication is a beta-blocker?",
    "options": [
      "A. Metoprolol",
      "B. Lisinopril",
      "C. Amlodipine",
      "D. Losartan"
    ],
    "answer": "A",
    "rationale": "Metoprolol is a selective beta-1 blocker."
  },
  {
    "number": 2,
    "topic": "Infection Control",
    "type": "SATA",
    "question": "Which are standard precautions? Select all that apply.",
    "options": [
      "A. Hand hygiene",
      "B. Use of PPE",
      "C. Reverse isolation",
      "D. Safe injection practices"
    ],
    "answer": ["A", "B", "D"],
    "rationale": "Standard precautions include hand hygiene, PPE, and safe injection practices."
  },
  {
    "number": 3,
    "topic": "Anatomy",
    "type": "FIB",
    "question": "The largest organ of the human body is the ____.",
    "answer": "skin",
    "rationale": "The skin is the largest organ by surface area."
  }
]`;

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  copyExample(): void {
    navigator.clipboard.writeText(this.exampleJson).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2000);
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      this.jsonText.set(reader.result as string);
      if (!this.title()) {
        const name = file.name.replace(/\.json$/i, '');
        this.title.set(name);
      }
    };
    reader.readAsText(file);
  }

  submit(): void {
    this.error.set('');
    const titleVal = this.title().trim();
    const jsonVal = this.jsonText().trim();

    if (!titleVal) {
      this.error.set('Please enter an exam title.');
      return;
    }
    if (!jsonVal) {
      this.error.set('Please paste or upload a JSON file.');
      return;
    }

    let questions: unknown[];
    try {
      questions = JSON.parse(jsonVal);
      if (!Array.isArray(questions) || questions.length === 0) throw new Error();
    } catch {
      this.error.set('Invalid JSON. Must be a non-empty array of question objects.');
      return;
    }

    this.loading.set(true);
    this.examService.createExam(titleVal, questions as never[]).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/exams']);
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || 'Failed to create exam.');
      },
    });
  }
}
