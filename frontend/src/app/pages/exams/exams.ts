import { Component, OnInit, signal, computed } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService, ExamSummary, Course } from '../../services/exam.service';

@Component({
  selector: 'app-exams',
  imports: [FormsModule],
  templateUrl: './exams.html',
  styleUrl: './exams.scss',
})
export class ExamsPage implements OnInit {
  exams = signal<ExamSummary[]>([]);
  courses = signal<Course[]>([]);
  selectedCourseId = signal<string>('');
  titleDrafts = signal<Record<string, string>>({});
  timeLimitDrafts = signal<Record<string, number | null>>({});
  questionCounts = signal<Record<string, number>>({});
  loadingRename = signal<Record<string, boolean>>({});
  renameError = signal<Record<string, string>>({});
  loadingTimeLimit = signal<Record<string, boolean>>({});
  timeLimitError = signal<Record<string, string>>({});
  menuOpen = signal<string | null>(null);
  editMode = signal<Record<string, 'rename' | 'count' | 'time-limit' | null>>({});
  searchQuery = signal('');
  loading = signal(true);
  loadError = signal('');
  deleteError = signal<Record<string, string>>({});

  filteredExams = computed(() => {
    const courseId = this.selectedCourseId();
    const query = this.searchQuery().toLowerCase().trim();
    const all = this.exams();
    return all.filter((e) => {
      const matchCourse = !courseId || e.course_id === courseId;
      const matchSearch =
        !query ||
        e.title.toLowerCase().includes(query) ||
        (e.course_name && e.course_name.toLowerCase().includes(query));
      return matchCourse && matchSearch;
    });
  });

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.loadCourses();
    this.load();
  }

  loadCourses(): void {
    // The course filter is a convenience — the exam list itself surfaces load failures.
    this.examService.listCourses().subscribe((data) => this.courses.set(data));
  }

  load(): void {
    this.loadError.set('');
    this.examService.listExams().subscribe({
      next: (data) => {
        this.exams.set(data);
        const titleDrafts: Record<string, string> = {};
        const limitDrafts: Record<string, number | null> = {};
        const counts: Record<string, number> = {};
        for (const exam of data) {
          titleDrafts[exam.id] = exam.title;
          limitDrafts[exam.id] = exam.time_limit_minutes;
          counts[exam.id] = counts[exam.id] ?? exam.total_questions;
        }
        this.titleDrafts.set(titleDrafts);
        this.timeLimitDrafts.set(limitDrafts);
        this.questionCounts.set(counts);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load exams.');
      },
    });
  }

  onCourseChange(courseId: string): void {
    this.selectedCourseId.set(courseId);
  }

  start(exam: ExamSummary, mode: 'exam' | 'practice'): void {
    this.menuOpen.set(null);
    if (mode === 'exam') {
      // A graded run is always the whole paper — the server ignores any subset,
      // because choosing one let a student be scored over only what they knew.
      this.router.navigate(['/exam', exam.id], { queryParams: { mode } });
      return;
    }
    const selected = this.questionCounts()[exam.id] ?? exam.total_questions;
    const count = Math.max(1, Math.min(exam.total_questions, Math.floor(selected)));
    this.router.navigate(['/exam', exam.id], { queryParams: { mode, count } });
  }

  toggleAllowPractice(exam: ExamSummary): void {
    this.menuOpen.set(null);
    if (exam.allow_practice) {
      const ok = confirm(
        'Make this exam assessment-only?\n\n' +
          'Practice mode and flashcards will be disabled, the answer key will no ' +
          'longer be sent to students, and any practice attempt in progress will ' +
          'stop saving.',
      );
      if (!ok) return;
    }
    this.examService.updateAllowPractice(exam.id, !exam.allow_practice).subscribe({
      next: () => this.load(),
      error: (err) => {
        this.deleteError.set({
          ...this.deleteError(),
          [exam.id]: err?.error?.detail || 'Could not change practice mode.',
        });
      },
    });
  }

  editQuestions(exam: ExamSummary): void {
    this.menuOpen.set(null);
    this.router.navigate(['/exams', exam.id, 'edit']);
  }

  openFlashcards(exam: ExamSummary): void {
    this.menuOpen.set(null);
    const selected = this.questionCounts()[exam.id] ?? exam.total_questions;
    const count = Math.max(1, Math.min(exam.total_questions, Math.floor(selected)));
    this.router.navigate(['/flashcards', exam.id], { queryParams: { count, shuffle: true } });
  }

  updateTitleDraft(examId: string, value: string): void {
    this.titleDrafts.set({ ...this.titleDrafts(), [examId]: value });
  }

  updateQuestionCount(exam: ExamSummary, value: string): void {
    const parsed = Number(value);
    const count = Number.isFinite(parsed)
      ? Math.max(1, Math.min(exam.total_questions, Math.floor(parsed)))
      : exam.total_questions;
    this.questionCounts.set({ ...this.questionCounts(), [exam.id]: count });
  }

  saveTitle(exam: ExamSummary, event: Event): void {
    event.stopPropagation();
    const title = (this.titleDrafts()[exam.id] ?? '').trim();
    if (!title) {
      this.renameError.set({ ...this.renameError(), [exam.id]: 'Title cannot be empty.' });
      return;
    }
    if (title === exam.title) return;

    this.loadingRename.set({ ...this.loadingRename(), [exam.id]: true });
    this.renameError.set({ ...this.renameError(), [exam.id]: '' });

    this.examService.renameExam(exam.id, title).subscribe({
      next: () => {
        this.loadingRename.set({ ...this.loadingRename(), [exam.id]: false });
        this.menuOpen.set(null);
        this.load();
      },
      error: (err) => {
        this.loadingRename.set({ ...this.loadingRename(), [exam.id]: false });
        this.renameError.set({
          ...this.renameError(),
          [exam.id]: err?.error?.detail || 'Rename failed.',
        });
      },
    });
  }

  updateTimeLimitDraft(id: string, val: number | null): void {
    this.timeLimitDrafts.set({ ...this.timeLimitDrafts(), [id]: val });
  }

  saveTimeLimit(exam: ExamSummary, event: Event): void {
    event.stopPropagation();
    let limit = this.timeLimitDrafts()[exam.id];
    if (limit && limit <= 0) limit = null;

    if (limit === exam.time_limit_minutes) return;

    this.loadingTimeLimit.set({ ...this.loadingTimeLimit(), [exam.id]: true });
    this.timeLimitError.set({ ...this.timeLimitError(), [exam.id]: '' });

    this.examService.updateTimeLimit(exam.id, limit).subscribe({
      next: () => {
        this.loadingTimeLimit.set({ ...this.loadingTimeLimit(), [exam.id]: false });
        this.menuOpen.set(null);
        this.load();
      },
      error: (err) => {
        this.loadingTimeLimit.set({ ...this.loadingTimeLimit(), [exam.id]: false });
        this.timeLimitError.set({
          ...this.timeLimitError(),
          [exam.id]: err?.error?.detail || 'Update failed.',
        });
      },
    });
  }

  toggleMenu(examId: string, event: Event): void {
    event.stopPropagation();
    if (this.menuOpen() === examId) {
      this.menuOpen.set(null);
      this.editMode.set({ ...this.editMode(), [examId]: null });
    } else {
      this.menuOpen.set(examId);
      this.editMode.set({ ...this.editMode(), [examId]: null });
    }
  }

  pickMenuOption(examId: string, option: 'rename' | 'count' | 'time-limit'): void {
    this.editMode.set({ ...this.editMode(), [examId]: option });
  }

  closeMenu(): void {
    const current = this.menuOpen();
    if (current) {
      this.editMode.set({ ...this.editMode(), [current]: null });
    }
    this.menuOpen.set(null);
  }

  remove(id: string, event: Event): void {
    event.stopPropagation();
    if (!confirm('Delete this exam and all of its questions?')) return;
    this.examService.deleteExam(id).subscribe({
      next: () => this.load(),
      error: (err) => {
        this.deleteError.set({
          ...this.deleteError(),
          [id]: err?.error?.detail || 'Delete failed.',
        });
      },
    });
  }
}
