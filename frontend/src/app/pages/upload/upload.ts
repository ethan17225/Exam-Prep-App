import { Component, OnInit, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService, Course } from '../../services/exam.service';

@Component({
  selector: 'app-upload',
  imports: [FormsModule],
  templateUrl: './upload.html',
  styleUrl: './upload.scss',
})
export class UploadPage implements OnInit {
  title = signal('');
  jsonText = signal('');
  error = signal('');
  loading = signal(false);
  showExample = signal(false);
  copied = signal(false);

  courses = signal<Course[]>([]);
  selectedCourseId = signal<string>('');
  showNewCourse = signal(false);
  newCourseName = signal('');
  courseLoading = signal(false);
  courseError = signal('');

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

  ngOnInit(): void {
    this.loadCourses();
  }

  loadCourses(): void {
    this.examService.listCourses().subscribe((data) => this.courses.set(data));
  }

  onCourseSelectChange(value: string): void {
    if (value === '__new__') {
      this.showNewCourse.set(true);
      this.selectedCourseId.set('');
    } else {
      this.showNewCourse.set(false);
      this.newCourseName.set('');
      this.courseError.set('');
      this.selectedCourseId.set(value);
    }
  }

  createNewCourse(): void {
    const name = this.newCourseName().trim();
    if (!name) {
      this.courseError.set('Course name cannot be empty.');
      return;
    }
    this.courseLoading.set(true);
    this.courseError.set('');
    this.examService.createCourse(name).subscribe({
      next: (course) => {
        this.courseLoading.set(false);
        this.courses.set([...this.courses(), course]);
        this.selectedCourseId.set(course.id);
        this.showNewCourse.set(false);
        this.newCourseName.set('');
      },
      error: (err) => {
        this.courseLoading.set(false);
        this.courseError.set(err?.error?.detail || 'Failed to create course.');
      },
    });
  }

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

    if (!this.selectedCourseId()) {
      this.error.set('Please select a course.');
      return;
    }
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
    this.examService.createExam(titleVal, questions as never[], this.selectedCourseId()).subscribe({
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
