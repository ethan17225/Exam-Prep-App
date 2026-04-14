import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { ExamService, AdminDashboardItem } from '../../services/exam.service';

@Component({
  selector: 'app-admin',
  imports: [],
  templateUrl: './admin.html',
  styleUrl: './admin.scss',
})
export class AdminPage implements OnInit, OnDestroy {
  items = signal<AdminDashboardItem[]>([]);
  private pollInterval: ReturnType<typeof setInterval> | null = null;
  private localTimerInterval: ReturnType<typeof setInterval> | null = null;
  localSeconds = signal<Map<string, number>>(new Map());

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
    this.examService.getAdminDashboard().subscribe((data) => {
      this.items.set(data);
      const m = new Map<string, number>();
      for (const item of data) {
        m.set(item.id, item.seconds_since_last_answer);
      }
      this.localSeconds.set(m);
    });
  }

  private tickLocalTimers(): void {
    const m = new Map(this.localSeconds());
    for (const [key, val] of m) {
      m.set(key, val + 1);
    }
    this.localSeconds.set(m);
  }

  progressPercent(item: AdminDashboardItem): number {
    if (item.total_questions === 0) return 0;
    return Math.round((item.answered_count / item.total_questions) * 100);
  }

  getIdleDuration(item: AdminDashboardItem): string {
    const secs = this.localSeconds().get(item.id) ?? item.seconds_since_last_answer;
    return this.formatDuration(secs);
  }

  getElapsedDuration(item: AdminDashboardItem): string {
    if (item.seconds_since_start == null) return '--';
    const localIdle = this.localSeconds().get(item.id) ?? item.seconds_since_last_answer;
    const elapsed = item.seconds_since_start + (localIdle - item.seconds_since_last_answer);
    return this.formatDuration(elapsed);
  }

  formatDuration(totalSec: number): string {
    if (totalSec < 60) return `${totalSec}s`;
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    if (mins < 60) return `${mins}m ${secs}s`;
    const hrs = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hrs}h ${remMins}m`;
  }

  formatTimerRemaining(seconds: number): string {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${pad(hrs)}:${pad(mins)}:${pad(secs)}`;
  }
}
