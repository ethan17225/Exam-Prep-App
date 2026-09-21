import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import {
  ExamService,
  AdminDashboardItem,
  formatClock,
  formatDuration,
  progressPercent,
} from '../../services/exam.service';

@Component({
  selector: 'app-tracking',
  imports: [],
  templateUrl: './tracking.html',
  styleUrl: './tracking.scss',
})
export class TrackingPage implements OnInit, OnDestroy {
  items = signal<AdminDashboardItem[]>([]);
  loading = signal(true);
  loadError = signal('');
  resetError = signal<Record<string, string>>({});
  resetting = signal<Record<string, boolean>>({});
  private pollInterval: ReturnType<typeof setInterval> | null = null;
  private localTimerInterval: ReturnType<typeof setInterval> | null = null;
  localSeconds = signal<Map<string, number>>(new Map());

  readonly formatClock = formatClock;
  readonly progressPercent = progressPercent;

  constructor(private examService: ExamService) {}

  ngOnInit(): void {
    this.load();
    this.pollInterval = setInterval(() => this.load(), 3000);
    this.localTimerInterval = setInterval(() => this.tickLocalTimers(), 1000);
  }

  ngOnDestroy(): void {
    if (this.pollInterval) clearInterval(this.pollInterval);
    if (this.localTimerInterval) clearInterval(this.localTimerInterval);
  }

  load(): void {
    this.examService.getAdminDashboard().subscribe({
      next: (data) => {
        this.items.set(data);
        const m = new Map<string, number>();
        for (const item of data) {
          m.set(item.id, item.seconds_since_last_answer);
        }
        this.localSeconds.set(m);
        this.loading.set(false);
        this.loadError.set('');
      },
      error: (err) => {
        this.loading.set(false);
        // A transient poll failure with data already on screen shouldn't blank the
        // dashboard — only surface the error when there is nothing to show.
        if (this.items().length === 0) {
          this.loadError.set(err?.error?.detail || 'Failed to load the dashboard.');
        }
      },
    });
  }

  private tickLocalTimers(): void {
    const m = new Map(this.localSeconds());
    for (const [key, val] of m) {
      m.set(key, val + 1);
    }
    this.localSeconds.set(m);
  }

  getIdleDuration(item: AdminDashboardItem): string {
    const secs = this.localSeconds().get(item.id) ?? item.seconds_since_last_answer;
    return formatDuration(secs);
  }

  getElapsedDuration(item: AdminDashboardItem): string {
    if (item.seconds_since_start == null) return '--';
    const localIdle = this.localSeconds().get(item.id) ?? item.seconds_since_last_answer;
    const elapsed = item.seconds_since_start + (localIdle - item.seconds_since_last_answer);
    return formatDuration(elapsed);
  }

  /**
   * Discard a student's open attempt so they can start the exam again.
   *
   * Instructors go through `/api/admin`. Admins are not instructors and do not
   * open this page; their audited reset lives under `/api/platform`.
   */
  resetLiveAttempt(item: AdminDashboardItem): void {
    const who = item.student_name || item.student_email || 'this student';
    if (
      !confirm(
        `Discard ${who}'s attempt at "${item.exam_title}"?\n\n` +
          `Their answers so far are lost and the attempt is not graded. ` +
          `They can then start the exam again.`,
      )
    ) {
      return;
    }

    this.resetting.set({ ...this.resetting(), [item.id]: true });
    this.resetError.set({ ...this.resetError(), [item.id]: '' });

    const request = this.examService.resetStudentAttempt(item.id);

    request.subscribe({
      next: () => {
        this.resetting.set({ ...this.resetting(), [item.id]: false });
        this.load();
      },
      error: (err) => {
        this.resetting.set({ ...this.resetting(), [item.id]: false });
        this.resetError.set({
          ...this.resetError(),
          [item.id]: err?.error?.detail || 'Reset failed.',
        });
      },
    });
  }
}
