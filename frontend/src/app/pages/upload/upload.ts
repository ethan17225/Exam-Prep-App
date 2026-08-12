import { Component, OnInit, computed, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';

import { Course, ExamService } from '../../services/exam.service';
import { EXAMPLE_TYPES, buildExampleJson } from './upload.examples';

/** Whether questions come from a pasted array or get added one at a time. */
type UploadMode = 'json' | 'manual';

/** The default pass mark, mirroring the backend's DEFAULT_PASS_GRADE. */
const DEFAULT_PASS_GRADE = 72;

@Component({
  selector: 'app-upload',
  imports: [FormsModule],
  templateUrl: './upload.html',
  styleUrl: './upload.scss',
})
export class UploadPage implements OnInit {
  mode = signal<UploadMode>('json');

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
  passGrade = signal<number | null>(DEFAULT_PASS_GRADE);

  readonly exampleTypes = EXAMPLE_TYPES;
  /** Empty means the "All" tab: every type is shown. */
  selectedTypes = signal<ReadonlySet<string>>(new Set());
  exampleJson = computed(() => buildExampleJson(this.selectedTypes()));

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

  setMode(mode: UploadMode): void {
    this.mode.set(mode);
    // The message almost certainly referred to the other mode's fields.
    this.error.set('');
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

  // ── JSON example filter ──

  isTypeSelected(type: string): boolean {
    return this.selectedTypes().has(type);
  }

  /** No type selected is the "All" state, so this is also "is All active". */
  get allTypesActive(): boolean {
    return this.selectedTypes().size === 0;
  }

  selectAllTypes(): void {
    this.selectedTypes.set(new Set());
  }

  toggleType(type: string): void {
    // Copy-on-write: mutating the Set in place would not change the signal's
    // reference, so the computed example would never recompute.
    const next = new Set(this.selectedTypes());
    if (next.has(type)) next.delete(type);
    else next.add(type);
    this.selectedTypes.set(next);
  }

  copyExample(): void {
    navigator.clipboard.writeText(this.exampleJson()).then(() => {
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

    if (!this.selectedCourseId()) {
      this.error.set('Please select a course.');
      return;
    }
    if (!titleVal) {
      this.error.set('Please enter an exam title.');
      return;
    }

    const grade = this.passGrade();
    if (grade == null || !Number.isFinite(grade) || grade < 1 || grade > 100) {
      this.error.set('Pass grade is required and must be between 1 and 100.');
      return;
    }

    let questions: unknown[] = [];
    if (this.mode() === 'json') {
      const jsonVal = this.jsonText().trim();
      if (!jsonVal) {
        this.error.set('Please paste or upload a JSON file.');
        return;
      }
      try {
        questions = JSON.parse(jsonVal);
        if (!Array.isArray(questions) || questions.length === 0) throw new Error();
      } catch {
        this.error.set('Invalid JSON. Must be a non-empty array of question objects.');
        return;
      }
    }

    this.loading.set(true);
    let timeLimit = this.timeLimitMinutes();
    if (timeLimit && timeLimit <= 0) timeLimit = null; // invalid times ignored

    const manual = this.mode() === 'manual';
    this.examService
      .createExam(
        titleVal,
        questions as never[],
        Math.round(grade),
        this.selectedCourseId(),
        timeLimit,
      )
      .subscribe({
        next: (res) => {
          this.loading.set(false);
          // Manual mode creates the exam empty and hands off to the question
          // editor, which is already the full-featured per-question form — there
          // is no second inline editor to keep in sync with it.
          if (manual) this.router.navigate(['/exams', res.exam_id, 'edit']);
          else this.router.navigate(['/exams']);
        },
        error: (err) => {
          this.loading.set(false);
          this.error.set(err?.error?.detail || 'Failed to create exam.');
        },
      });
  }
}
