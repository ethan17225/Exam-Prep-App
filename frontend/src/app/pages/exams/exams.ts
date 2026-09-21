import { Component, OnInit, signal, computed } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';
import { ExamService, ExamSummary, Course, KindCount } from '../../services/exam.service';

@Component({
  selector: 'app-exams',
  imports: [FormsModule, RouterLink],
  templateUrl: './exams.html',
  styleUrl: './exams.scss',
})
export class ExamsPage implements OnInit {
  exams = signal<ExamSummary[]>([]);
  courses = signal<Course[]>([]);
  selectedCourseId = signal<string>('');
  titleDrafts = signal<Record<string, string>>({});
  loadingRename = signal<Record<string, boolean>>({});
  renameError = signal<Record<string, string>>({});
  menuOpen = signal<string | null>(null);
  editMode = signal<Record<string, 'rename' | null>>({});
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
    private auth: AuthService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.loadCourses();
    this.load();
  }

  isInstructor(): boolean {
    return this.auth.isInstructor();
  }

  /** Students only get the ⋮ menu on exams they own; instructor-shared ones are take-only. */
  showMenu(exam: ExamSummary): boolean {
    return exam.is_owner;
  }

  kindCounts(exam: ExamSummary): KindCount[] {
    return exam.kind_counts?.length
      ? exam.kind_counts
      : [
          ...(exam.mcq_count ? [{ kind: 'MCQ', count: exam.mcq_count }] : []),
          ...(exam.sata_count ? [{ kind: 'SATA', count: exam.sata_count }] : []),
          ...(exam.fib_count ? [{ kind: 'FIB', count: exam.fib_count }] : []),
          ...(exam.other_count ? [{ kind: 'Other', count: exam.other_count }] : []),
        ];
  }

  /** How many questions a student actually sits, given the exam's attempt size. */
  attemptSize(exam: ExamSummary): number {
    if (exam.questions_per_attempt == null) return exam.total_questions;
    return Math.max(1, Math.min(exam.total_questions, exam.questions_per_attempt));
  }

  chipTone(kind: string): 'mcq' | 'sata' | 'fib' | 'other' {
    if (kind === 'MCQ') return 'mcq';
    if (kind === 'SATA') return 'sata';
    if (kind === 'FIB') return 'fib';
    return 'other';
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
        for (const exam of data) {
          titleDrafts[exam.id] = exam.title;
        }
        this.titleDrafts.set(titleDrafts);
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
    this.router.navigate(['/exam', exam.id], { queryParams: { mode } });
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
    if (exam.bank_id) {
      this.router.navigate(['/banks', exam.bank_id]);
      return;
    }
    this.router.navigate(['/exams', exam.id, 'edit']);
  }

  editExamSettings(exam: ExamSummary): void {
    this.menuOpen.set(null);
    this.router.navigate(['/exams', exam.id, 'edit']);
  }

  openFlashcards(exam: ExamSummary): void {
    this.menuOpen.set(null);
    const count = exam.questions_per_attempt
      ? Math.max(1, Math.min(exam.total_questions, exam.questions_per_attempt))
      : exam.total_questions;
    this.router.navigate(['/flashcards', exam.id], {
      queryParams: { count, shuffle: exam.shuffle },
    });
  }

  updateTitleDraft(examId: string, value: string): void {
    this.titleDrafts.set({ ...this.titleDrafts(), [examId]: value });
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
        this.editMode.set({ ...this.editMode(), [exam.id]: null });
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

  pickMenuOption(examId: string, option: 'rename'): void {
    this.editMode.set({ ...this.editMode(), [examId]: option });
    this.menuOpen.set(null);
  }

  closeMenu(): void {
    this.menuOpen.set(null);
  }

  remove(exam: ExamSummary): void {
    this.menuOpen.set(null);
    if (!confirm('Delete this exam and all of its questions?')) return;
    this.examService.deleteExam(exam.id).subscribe({
      next: () => this.load(),
      error: (err) => {
        this.deleteError.set({
          ...this.deleteError(),
          [exam.id]: err?.error?.detail || 'Delete failed.',
        });
      },
    });
  }
}
