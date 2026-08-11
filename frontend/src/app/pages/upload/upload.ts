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
  timeLimitMinutes = signal<number | null>(null);

  readonly exampleJson = `[
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
  },
  {
    "number": 4,
    "topic": "Endocrine",
    "type": "MATRIX",
    "question": "For each finding, check the matching diabetes type.",
    "options": {
      "rows": ["HgA1C 6.8%", "BMI 35.9"],
      "columns": ["Type 1 Diabetes", "Type 2 Diabetes"]
    },
    "answer": { "0": ["Type 1 Diabetes", "Type 2 Diabetes"], "1": ["Type 2 Diabetes"] },
    "rationale": "Answer keys map row index to the correct column(s)."
  },
  {
    "number": 5,
    "topic": "Diabetes",
    "type": "CLOZE",
    "question": "The client should be instructed to [1] and [2] if the blood sugar is 60 mg/dL.",
    "options": {
      "blanks": [
        { "label": "Dropdown 1", "choices": ["fast", "drink orange juice", "call 911"] },
        { "label": "Dropdown 2", "choices": ["continue to monitor symptoms", "drink four glasses of water"] }
      ]
    },
    "answer": ["drink orange juice", "continue to monitor symptoms"],
    "rationale": "One answer per blank, in order."
  },
  {
    "number": 6,
    "topic": "Newborn",
    "type": "BOWTIE",
    "question": "Drag one condition and two interventions.",
    "options": {
      "categories": [
        { "name": "Potential Condition", "count": 1, "choices": ["Acrocyanosis", "Meconium aspiration syndrome"] },
        { "name": "Potential Interventions", "count": 2, "choices": ["Suctioning", "Oxygen therapy", "Phototherapy"] }
      ]
    },
    "answer": {
      "Potential Condition": ["Meconium aspiration syndrome"],
      "Potential Interventions": ["Suctioning", "Oxygen therapy"]
    },
    "rationale": "Answer keys map category name to the correct choice(s)."
  },
  {
    "number": 7,
    "topic": "Urinary",
    "type": "RANKING",
    "question": "Rank from highest risk to lowest risk for UTI.",
    "options": ["Older males", "School-age female", "Older females", "Adolescent males"],
    "answer": ["Older females", "Older males", "School-age female", "Adolescent males"],
    "rationale": "Options is the display order; answer is the correct order."
  },
  {
    "number": 8,
    "topic": "Assessment",
    "type": "HIGHLIGHT",
    "question": "Click to highlight the findings that require follow-up.",
    "options": {
      "tokens": ["Blood pressure 160/100 mm Hg", "Heart rate 88 beats/min", "BMI 35.9 kg/m2"]
    },
    "answer": [0, 2],
    "rationale": "Answer is the list of correct token indices (0-based)."
  },
  {
    "number": 9,
    "topic": "Pediatrics",
    "type": "HOTSPOT",
    "question": "Click the location where the nurse should pull the pinna.",
    "options": {
      "regions": [
        { "id": "r1", "label": "Up and back", "x": 55, "y": 5, "w": 40, "h": 30 },
        { "id": "r2", "label": "Down and back", "x": 55, "y": 60, "w": 40, "h": 30 }
      ]
    },
    "answer": "r2",
    "rationale": "Region coordinates are percentages of the image. Upload the image afterwards via Edit Questions."
  },
  {
    "number": 10,
    "topic": "Hypoglycemia Management",
    "type": "MCQ",
    "question": "The client is alert and able to swallow. Which action should the nurse take first?",
    "sections": [
      {
        "title": "Nurses' Notes",
        "blocks": [
          { "type": "text", "text": "1030: Client reports feeling shaky and sweaty. Skin cool and diaphoretic. Last meal at 0700." },
          { "type": "list", "items": ["Alert and oriented x3", "Able to swallow without difficulty", "Fine tremor of both hands"] }
        ]
      },
      {
        "title": "Laboratory Results",
        "blocks": [
          {
            "type": "table",
            "caption": "Point-of-care glucose",
            "headers": ["Lab Test", "0800", "1030", "Reference Range"],
            "rows": [
              ["Blood glucose", "101 mg/dL", "58 mg/dL", "74-140 mg/dL"],
              ["Hemoglobin A1C", "7.2%", "-", "Less than 5.7%"]
            ]
          }
        ]
      }
    ],
    "options": [
      "A. Give 15 g of a fast-acting carbohydrate and recheck in 15 minutes.",
      "B. Administer 1 mg of glucagon intramuscularly.",
      "C. Hold the next dose of insulin and notify the provider.",
      "D. Provide a peanut butter sandwich and whole milk."
    ],
    "answer": "A",
    "rationale": "Sections are optional on any question type. Two or more sections render as tabs above the question."
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
    this.examService.listCourses().subscribe({
      next: (data) => this.courses.set(data),
      // A course is required to submit, so a failed load must not look like "no courses yet".
      error: (err) =>
        this.courseError.set(
          err?.error?.detail || 'Failed to load courses — reload the page to retry.',
        ),
    });
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
    let timeLimit = this.timeLimitMinutes();
    if (timeLimit && timeLimit <= 0) timeLimit = null; // invalid times ignored

    this.examService
      .createExam(titleVal, questions as never[], this.selectedCourseId(), timeLimit)
      .subscribe({
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
