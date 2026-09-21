import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Observable } from 'rxjs';

import { AdminTabsComponent } from '../../components/admin-tabs/admin-tabs';
import {
  AdminCourse,
  AdminExam,
  AdminInstructor,
  ExamService,
  formatDate,
} from '../../services/exam.service';

const PAGE_SIZE = 25;

type Tab = 'exams' | 'courses';
/** Tri-state sharing filter. '' is "either", which is not the same as false. */
type SharedFilter = '' | 'shared' | 'private';

/**
 * Content oversight across every owner.
 *
 * The distinguishing feature versus the normal Exams page is that nothing here is
 * filtered by the visibility predicate — an admin sees private drafts belonging
 * to other people, which is the whole point of a moderation view, and is why
 * these reads live behind the admin gate rather than being folded into
 * `/api/exams`.
 */
@Component({
  selector: 'app-admin-content',
  imports: [FormsModule, AdminTabsComponent],
  templateUrl: './admin-content.html',
  styleUrl: './admin-content.scss',
})
export class AdminContentPage implements OnInit {
  tab = signal<Tab>('exams');

  exams = signal<AdminExam[]>([]);
  courses = signal<AdminCourse[]>([]);
  total = signal(0);
  offset = signal(0);
  loading = signal(true);
  loadError = signal('');

  search = signal('');
  sharedFilter = signal<SharedFilter>('');

  /** Transfer targets. Only staff can own shared content, so only staff appear. */
  instructors = signal<AdminInstructor[]>([]);

  rowBusy = signal<Record<string, boolean>>({});
  rowError = signal<Record<string, string>>({});

  readonly formatDate = formatDate;
  readonly pageSize = PAGE_SIZE;

  constructor(private examService: ExamService) {}

  ngOnInit(): void {
    this.load();
    this.examService.listAdminInstructors().subscribe({
      next: (rows) => this.instructors.set(rows),
      error: () => {},
    });
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    const query = this.search().trim();

    if (this.tab() === 'exams') {
      const shared = this.sharedFilter() === '' ? null : this.sharedFilter() === 'shared';
      this.examService.listAdminExams(query, shared, PAGE_SIZE, this.offset()).subscribe({
        next: (page) => {
          this.exams.set(page.items);
          this.total.set(page.total);
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          this.loadError.set(err?.error?.detail || 'Failed to load exams.');
        },
      });
      return;
    }

    this.examService.listAdminCourses(query, PAGE_SIZE, this.offset()).subscribe({
      next: (page) => {
        this.courses.set(page.items);
        this.total.set(page.total);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load courses.');
      },
    });
  }

  switchTab(tab: Tab): void {
    if (this.tab() === tab) return;
    this.tab.set(tab);
    this.offset.set(0);
    this.load();
  }

  /** Any filter change resets to the first page, or the view can land past the end. */
  applyFilters(): void {
    this.offset.set(0);
    this.load();
  }

  setSharedFilter(value: SharedFilter): void {
    this.sharedFilter.set(value);
    this.applyFilters();
  }

  page(delta: number): void {
    const next = this.offset() + delta * PAGE_SIZE;
    if (next < 0 || next >= this.total()) return;
    this.offset.set(next);
    this.load();
  }

  rangeStart(): number {
    return this.total() === 0 ? 0 : this.offset() + 1;
  }

  rangeEnd(): number {
    return Math.min(this.offset() + PAGE_SIZE, this.total());
  }

  // ── Exam actions ──────────────────────────────────────────────

  toggleExamShared(exam: AdminExam): void {
    const next = !exam.is_shared;
    const verb = next ? 'Publish' : 'Unpublish';
    if (
      !confirm(
        `${verb} "${exam.title}"? ${next ? 'Everyone will see it.' : 'Only its owner will see it.'}`,
      )
    ) {
      return;
    }
    this.run(exam.id, this.examService.updateAdminExam(exam.id, { is_shared: next }));
  }

  transferExam(exam: AdminExam, ownerId: string): void {
    if (!ownerId || ownerId === exam.owner_id) return;
    if (!confirm(`Transfer "${exam.title}" to the selected instructor?`)) return;
    this.run(exam.id, this.examService.updateAdminExam(exam.id, { owner_id: ownerId }));
  }

  deleteExam(exam: AdminExam): void {
    const warning =
      `Permanently delete "${exam.title}"?\n\n` +
      `Its ${exam.total_questions} question(s) and their images go too. ` +
      `Attempt history survives — past marks are not erased.\n\nThis cannot be undone.`;
    if (!confirm(warning)) return;
    this.run(exam.id, this.examService.deleteAdminExam(exam.id));
  }

  // ── Course actions ────────────────────────────────────────────

  toggleCourseShared(course: AdminCourse): void {
    const next = !course.is_shared;
    if (!confirm(`${next ? 'Publish' : 'Unpublish'} "${course.name}"?`)) return;
    this.run(course.id, this.examService.updateAdminCourse(course.id, { is_shared: next }));
  }

  transferCourse(course: AdminCourse, ownerId: string): void {
    if (!ownerId || ownerId === course.owner_id) return;
    if (!confirm(`Transfer "${course.name}" to the selected instructor?`)) return;
    this.run(course.id, this.examService.updateAdminCourse(course.id, { owner_id: ownerId }));
  }

  deleteCourse(course: AdminCourse): void {
    const warning =
      `Delete the course "${course.name}"?\n\n` +
      `Its exams are not deleted — they become unfiled.`;
    if (!confirm(warning)) return;
    this.run(course.id, this.examService.deleteAdminCourse(course.id));
  }

  /** Shared busy/error bookkeeping, then refetch rather than patch the row. */
  private run(id: string, request: Observable<unknown>): void {
    this.rowBusy.set({ ...this.rowBusy(), [id]: true });
    this.rowError.set({ ...this.rowError(), [id]: '' });
    request.subscribe({
      next: () => {
        this.rowBusy.set({ ...this.rowBusy(), [id]: false });
        this.load();
      },
      error: (err: { error?: { detail?: string } }) => {
        this.rowBusy.set({ ...this.rowBusy(), [id]: false });
        this.rowError.set({
          ...this.rowError(),
          [id]: err?.error?.detail || 'That action failed.',
        });
      },
    });
  }
}
