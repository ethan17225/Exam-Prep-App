import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AdminTabsComponent } from '../../components/admin-tabs/admin-tabs';
import {
  AuditEntry,
  ExamService,
  formatAuditAction,
  formatDate,
} from '../../services/exam.service';

const PAGE_SIZES = [20, 50, 100] as const;
type PageSize = (typeof PAGE_SIZES)[number];

/**
 * Filter chips. The values are server-side prefix matches, not exact actions.
 *
 * One chip per area in the backend's AUDIT_AREAS, which a test pins: an action
 * added in an area with no chip here would only ever be visible under "All".
 */
const FILTERS: { label: string; prefix: string }[] = [
  { label: 'All', prefix: '' },
  { label: 'Accounts', prefix: 'user.' },
  { label: 'Instructors', prefix: 'instructor.' },
  { label: 'Exams', prefix: 'exam.' },
  { label: 'Courses', prefix: 'course.' },
  { label: 'Attempts', prefix: 'attempt.' },
];

/**
 * The audit log: who did what, when.
 *
 * Read-only by design — the backend exposes no route that edits or removes an
 * entry, because an audit trail an admin can rewrite is not one.
 *
 * Lazy: only the current page is fetched. Changing the filter, page, or page
 * size requests that slice and nothing else. Users, by contrast, load their
 * first page on init the same way they always have.
 */
@Component({
  selector: 'app-admin-audit',
  imports: [FormsModule, AdminTabsComponent],
  templateUrl: './admin-audit.html',
  styleUrl: './admin-audit.scss',
})
export class AdminAuditPage implements OnInit {
  entries = signal<AuditEntry[]>([]);
  total = signal(0);
  offset = signal(0);
  pageSize = signal<PageSize>(20);
  loading = signal(true);
  loadError = signal('');
  filter = signal('');

  readonly formatDate = formatDate;
  readonly formatAuditAction = formatAuditAction;
  readonly filters = FILTERS;
  readonly pageSizes = PAGE_SIZES;

  constructor(private examService: ExamService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.listAudit(this.filter(), this.pageSize(), this.offset()).subscribe({
      next: (page) => {
        this.entries.set(page.items);
        this.total.set(page.total);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load the audit log.');
      },
    });
  }

  setFilter(prefix: string): void {
    this.filter.set(prefix);
    // A filter change resets to the first page, or the view can land past the end.
    this.offset.set(0);
    this.load();
  }

  setPageSize(size: number): void {
    if (size !== 20 && size !== 50 && size !== 100) return;
    if (this.pageSize() === size) return;
    this.pageSize.set(size);
    this.offset.set(0);
    this.load();
  }

  page(delta: number): void {
    const next = this.offset() + delta * this.pageSize();
    if (next < 0 || next >= this.total()) return;
    this.offset.set(next);
    this.load();
  }

  rangeStart(): number {
    return this.total() === 0 ? 0 : this.offset() + 1;
  }

  rangeEnd(): number {
    return Math.min(this.offset() + this.pageSize(), this.total());
  }

  /** "from=student, to=instructor" — the detail blob is free-form per action. */
  formatDetail(detail: Record<string, unknown>): string {
    return Object.entries(detail)
      .map(([key, value]) => `${key.replace(/_/g, ' ')}: ${value}`)
      .join(' · ');
  }

  /** Colour class per area, so a page of entries is scannable. */
  areaClass(action: string): string {
    // A reset is grouped with the deletes rather than with its own area: it
    // destroys the answers a student had entered, which is what the colour warns
    // about, not which table the row was in.
    if (action.endsWith('.deleted') || action === 'attempt.reset') return 'area-danger';
    if (action.startsWith('user.')) return 'area-user';
    if (action.startsWith('instructor.')) return 'area-instructor';
    return 'area-content';
  }
}
