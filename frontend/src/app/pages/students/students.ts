import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  ExamService,
  StudentDetail,
  StudentItem,
  TOPIC_MASTERY_THRESHOLD,
  formatDate,
  formatDuration,
} from '../../services/exam.service';
import { initialsOf } from '../../services/auth.service';

/** Sortable columns. The values double as the labels' `data-sort` keys. */
type SortKey = 'name' | 'attempts' | 'average_score' | 'pass_rate' | 'last_attempt_at';

@Component({
  selector: 'app-students',
  imports: [FormsModule],
  templateUrl: './students.html',
  styleUrl: './students.scss',
})
export class StudentsPage implements OnInit {
  students = signal<StudentItem[]>([]);
  loading = signal(true);
  loadError = signal('');

  search = signal('');
  sortKey = signal<SortKey>('name');
  sortDesc = signal(false);

  /** Which row is expanded, and the detail for it. One at a time. */
  expandedId = signal<string | null>(null);
  detail = signal<StudentDetail | null>(null);
  detailLoading = signal(false);
  detailError = signal('');

  readonly formatDate = formatDate;
  readonly formatDuration = formatDuration;
  readonly masteryThreshold = TOPIC_MASTERY_THRESHOLD;
  readonly initialsOf = initialsOf;

  /**
   * Filter then sort, both client-side: the roster is one class, and doing it here
   * keeps typing in the search box instant with no request per keystroke.
   */
  visible = computed(() => {
    const query = this.search().trim().toLowerCase();
    const rows = query
      ? this.students().filter(
          (s) =>
            (s.display_name ?? '').toLowerCase().includes(query) ||
            s.email.toLowerCase().includes(query),
        )
      : [...this.students()];

    const key = this.sortKey();
    const direction = this.sortDesc() ? -1 : 1;
    rows.sort((a, b) => direction * compareBy(key, a, b));
    return rows;
  });

  weakestTopics = computed(() => [...(this.detail()?.topic_stats ?? [])].reverse().slice(0, 5));

  constructor(private examService: ExamService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.getStudents().subscribe({
      next: (rows) => {
        this.students.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load your students.');
      },
    });
  }

  sortBy(key: SortKey): void {
    if (this.sortKey() === key) {
      this.sortDesc.update((desc) => !desc);
      return;
    }
    this.sortKey.set(key);
    // Names read best A-Z; every metric reads best highest-first.
    this.sortDesc.set(key !== 'name');
  }

  sortIndicator(key: SortKey): string {
    if (this.sortKey() !== key) return '';
    return this.sortDesc() ? '↓' : '↑';
  }

  /** Expanding fetches the drill-down; collapsing drops it so a reopen is fresh. */
  toggle(student: StudentItem): void {
    if (this.expandedId() === student.id) {
      this.expandedId.set(null);
      this.detail.set(null);
      return;
    }

    this.expandedId.set(student.id);
    this.detail.set(null);
    this.detailError.set('');
    this.detailLoading.set(true);
    this.examService.getStudentDetail(student.id).subscribe({
      next: (detail) => {
        // Ignore a response that arrived after the user moved on to another row.
        if (this.expandedId() !== student.id) return;
        this.detail.set(detail);
        this.detailLoading.set(false);
      },
      error: (err) => {
        if (this.expandedId() !== student.id) return;
        this.detailLoading.set(false);
        this.detailError.set(err?.error?.detail || 'Failed to load this student.');
      },
    });
  }
}

function compareBy(key: SortKey, a: StudentItem, b: StudentItem): number {
  switch (key) {
    case 'name':
      return (a.display_name || a.email).localeCompare(b.display_name || b.email);
    case 'last_attempt_at':
      // Never-attempted sorts last either way rather than jumping to the top on
      // a descending sort, which is where an empty string would put it.
      return (a.last_attempt_at ?? '').localeCompare(b.last_attempt_at ?? '');
    default:
      return a[key] - b[key];
  }
}
