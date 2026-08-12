import { Component, OnDestroy, OnInit, computed, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  DoughnutController,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js';

import {
  ExamService,
  InstructorOverview,
  TOPIC_MASTERY_THRESHOLD,
  formatDate,
  formatDuration,
} from '../../services/exam.service';

// Only the pieces the four charts below use — `registerables` would pull all of
// chart.js (~220 kB) onto the instructor's landing route.
Chart.register(
  LineController,
  LineElement,
  PointElement,
  BarController,
  BarElement,
  DoughnutController,
  ArcElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
  Filler,
);

/** How many of the weakest topics the class-wide list shows. */
const WEAK_TOPIC_LIMIT = 6;

@Component({
  selector: 'app-instructor-overview',
  imports: [],
  templateUrl: './instructor-overview.html',
  styleUrl: './instructor-overview.scss',
})
export class InstructorOverviewPage implements OnInit, OnDestroy {
  data = signal<InstructorOverview | null>(null);
  loading = signal(true);
  loadError = signal('');
  codeCopied = signal(false);

  private charts: Chart[] = [];

  readonly formatDate = formatDate;
  readonly formatDuration = formatDuration;
  readonly masteryThreshold = TOPIC_MASTERY_THRESHOLD;

  /**
   * Weakest topics first. The API sorts strongest-first for the student's own
   * chart; an instructor cares about what to reteach.
   */
  weakestTopics = computed(() =>
    [...(this.data()?.topic_stats ?? [])].reverse().slice(0, WEAK_TOPIC_LIMIT),
  );

  /** Nobody has enrolled yet, so the page shows the invite code instead of zeros. */
  isEmptyClass = computed(() => (this.data()?.student_count ?? 0) === 0);

  /** Enrolled students but no attempts: the charts would all be blank. */
  hasNoAttempts = computed(() => (this.data()?.attempts ?? 0) === 0);

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  ngOnDestroy(): void {
    this.destroyCharts();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.getInstructorOverview().subscribe({
      next: (data) => {
        this.data.set(data);
        this.loading.set(false);
        // After the template has rendered the canvases this reads by id.
        setTimeout(() => this.renderCharts(), 0);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load your dashboard.');
      },
    });
  }

  openStudents(): void {
    this.router.navigate(['/students']);
  }

  openTracking(): void {
    this.router.navigate(['/tracking']);
  }

  copyInviteCode(): void {
    const code = this.data()?.invite_code;
    if (!code) return;
    navigator.clipboard.writeText(code).then(() => {
      this.codeCopied.set(true);
      setTimeout(() => this.codeCopied.set(false), 2000);
    });
  }

  /** "3h 20m" of class time, from a total that can run to hundreds of hours. */
  studyTime(): string {
    const seconds = this.data()?.total_seconds ?? 0;
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  }

  private destroyCharts(): void {
    this.charts.forEach((c) => c.destroy());
    this.charts = [];
  }

  private renderCharts(): void {
    this.destroyCharts();
    if (this.hasNoAttempts()) return;

    this.renderActivity();
    this.renderOutcome();
    this.renderDistribution();
    this.renderTopics();
  }

  private renderActivity(): void {
    const canvas = document.getElementById('activityChart') as HTMLCanvasElement | null;
    const points = this.data()?.attempts_per_day ?? [];
    if (!canvas || points.length === 0) return;

    this.charts.push(
      new Chart(canvas, {
        type: 'line',
        data: {
          // "Mon 4" — the full ISO date does not fit 14 labels on a phone.
          labels: points.map((p) => shortDay(p.day)),
          datasets: [
            {
              label: 'Attempts',
              data: points.map((p) => p.attempts),
              borderColor: '#4361ee',
              backgroundColor: 'rgba(67, 97, 238, 0.08)',
              fill: true,
              tension: 0.35,
              pointRadius: 3,
              borderWidth: 2,
              yAxisID: 'y',
            },
            {
              label: 'Average score',
              data: points.map((p) => p.average_score),
              borderColor: '#0a7',
              borderWidth: 2,
              borderDash: [5, 4],
              pointRadius: 0,
              fill: false,
              yAxisID: 'yScore',
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { position: 'bottom', labels: { usePointStyle: true, pointStyle: 'circle' } },
          },
          scales: {
            // Two axes: attempt counts are single digits while scores run to 100,
            // and on one axis the count line flattens onto the floor.
            y: {
              beginAtZero: true,
              ticks: { precision: 0 },
              grid: { color: '#f0f0f0' },
              title: { display: true, text: 'Attempts' },
            },
            yScore: {
              position: 'right',
              min: 0,
              max: 100,
              ticks: { callback: (v) => `${v}%` },
              grid: { display: false },
            },
            x: { grid: { display: false } },
          },
        },
      }),
    );
  }

  private renderOutcome(): void {
    const canvas = document.getElementById('outcomeChart') as HTMLCanvasElement | null;
    const data = this.data();
    if (!canvas || !data) return;

    this.charts.push(
      new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels: ['Passed', 'Failed'],
          datasets: [
            {
              data: [data.passed_count, data.failed_count],
              backgroundColor: ['#0a7', '#e5484d'],
              borderWidth: 0,
              hoverOffset: 6,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '65%',
          plugins: {
            legend: {
              position: 'bottom',
              labels: { padding: 14, usePointStyle: true, pointStyle: 'circle' },
            },
          },
        },
      }),
    );
  }

  private renderDistribution(): void {
    const canvas = document.getElementById('bucketChart') as HTMLCanvasElement | null;
    const buckets = this.data()?.score_buckets ?? [];
    if (!canvas || buckets.length === 0) return;

    this.charts.push(
      new Chart(canvas, {
        type: 'bar',
        data: {
          labels: buckets.map((_, i) => `${i * 10}-${i * 10 + 10}`),
          datasets: [
            {
              label: 'Attempts',
              data: buckets,
              backgroundColor: buckets.map((_, i) =>
                i >= 8 ? '#0a7' : i >= 5 ? '#4361ee' : '#e8e8e8',
              ),
              borderRadius: 4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#f0f0f0' } },
            x: { grid: { display: false } },
          },
        },
      }),
    );
  }

  private renderTopics(): void {
    const canvas = document.getElementById('topicChart') as HTMLCanvasElement | null;
    const topics = this.weakestTopics();
    if (!canvas || topics.length === 0) return;

    this.charts.push(
      new Chart(canvas, {
        type: 'bar',
        data: {
          labels: topics.map((t) => t.topic || 'Untitled'),
          datasets: [
            {
              label: 'Class score %',
              data: topics.map((t) => t.score),
              backgroundColor: topics.map((t) =>
                t.score >= this.masteryThreshold ? '#4361ee' : '#e5a00d',
              ),
              borderRadius: 4,
            },
          ],
        },
        options: {
          // Horizontal: topic names are sentences and unreadable rotated 90°.
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              min: 0,
              max: 100,
              ticks: { callback: (v) => `${v}%` },
              grid: { color: '#f0f0f0' },
            },
            y: { grid: { display: false } },
          },
        },
      }),
    );
  }
}

/** "2026-08-11" -> "Tue 11". */
function shortDay(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  return date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' });
}
