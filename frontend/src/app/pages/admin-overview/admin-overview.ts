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

import { AdminTabsComponent } from '../../components/admin-tabs/admin-tabs';
import {
  httpErrorDetail,
  ExamService,
  PlatformOverview,
  TOPIC_MASTERY_THRESHOLD,
  formatDate,
  formatDuration,
} from '../../services/exam.service';

// Only the pieces the three charts below use — `registerables` would pull all of
// chart.js (~220 kB) onto the admin's landing route.
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

/**
 * The admin landing page: one request, every deployment-wide number.
 *
 * Deliberately the *same* shape as the instructor overview rather than something
 * new — an admin reading both should not have to learn two layouts — but every
 * figure here spans all instructors, and the per-instructor table at the bottom
 * is the part that has no instructor-side equivalent.
 */
@Component({
  selector: 'app-admin-overview',
  imports: [AdminTabsComponent],
  templateUrl: './admin-overview.html',
  styleUrl: './admin-overview.scss',
})
export class AdminOverviewPage implements OnInit, OnDestroy {
  data = signal<PlatformOverview | null>(null);
  loading = signal(true);
  loadError = signal('');

  private charts: Chart[] = [];

  readonly formatDate = formatDate;
  readonly formatDuration = formatDuration;
  readonly masteryThreshold = TOPIC_MASTERY_THRESHOLD;

  /** Nobody has submitted anything, so every chart would render blank. */
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
    this.examService.getPlatformOverview().subscribe({
      next: (data) => {
        this.data.set(data);
        this.loading.set(false);
        // After the template has rendered the canvases this reads by id.
        setTimeout(() => this.renderCharts(), 0);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(httpErrorDetail(err) || 'Failed to load the platform dashboard.');
      },
    });
  }

  openUsers(role: string): void {
    this.router.navigate(['/admin/users'], { queryParams: role ? { role } : {} });
  }

  openContent(): void {
    this.router.navigate(['/admin/content']);
  }

  /** "3h 20m" of platform time, from a total that can run to thousands of hours. */
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
  }

  private renderActivity(): void {
    const canvas = document.getElementById('platformActivityChart') as HTMLCanvasElement | null;
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
            // Two axes: attempt counts are small integers while scores run to 100,
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
    const canvas = document.getElementById('platformOutcomeChart') as HTMLCanvasElement | null;
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
    const canvas = document.getElementById('platformBucketChart') as HTMLCanvasElement | null;
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
}

/** "2026-08-11" -> "Tue 11". */
function shortDay(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  return date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' });
}
