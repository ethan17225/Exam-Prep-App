import { Component, OnInit, OnDestroy, signal, computed } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService, ExamResult } from '../../services/exam.service';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

interface TopicStat {
  topic: string;
  score: number;
  correct: number;
  total: number;
}

@Component({
  selector: 'app-overview',
  imports: [FormsModule],
  templateUrl: './overview.html',
  styleUrl: './overview.scss',
})
export class OverviewPage implements OnInit, OnDestroy {
  records = signal<ExamResult[]>([]);
  selectedTopic = signal('');
  topicSearch = signal('');
  topicDropdownOpen = signal(false);
  private charts: Chart[] = [];

  totalExams = computed(() => this.records().length);

  averageScore = computed(() => {
    const r = this.records();
    if (r.length === 0) return 0;
    return Math.round((r.reduce((s, rec) => s + rec.score, 0) / r.length) * 10) / 10;
  });

  passRate = computed(() => {
    const r = this.records();
    if (r.length === 0) return 0;
    return Math.round((r.filter((rec) => rec.passed).length / r.length) * 100);
  });

  totalStudySeconds = computed(() => this.records().reduce((s, rec) => s + rec.time_spent_seconds, 0));

  formattedStudyTime = computed(() => {
    const secs = this.totalStudySeconds();
    const hrs = Math.floor(secs / 3600);
    const mins = Math.floor((secs % 3600) / 60);
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
  });

  examCount = computed(() => this.records().filter((r) => r.mode !== 'practice').length);
  practiceCount = computed(() => this.records().filter((r) => r.mode === 'practice').length);

  topicStats = computed<TopicStat[]>(() => {
    const map = new Map<string, { correct: number; total: number }>();
    for (const record of this.records()) {
      for (const q of record.results) {
        const existing = map.get(q.topic) || { correct: 0, total: 0 };
        existing.total++;
        if (q.is_correct) existing.correct++;
        map.set(q.topic, existing);
      }
    }
    return Array.from(map.entries())
      .map(([topic, stats]) => ({
        topic,
        score: Math.round((stats.correct / stats.total) * 100),
        correct: stats.correct,
        total: stats.total,
      }))
      .sort((a, b) => b.score - a.score);
  });

  filteredTopicStats = computed(() => {
    const query = this.topicSearch().trim().toLowerCase();
    if (!query) return this.topicStats();
    return this.topicStats().filter((t) => t.topic.toLowerCase().includes(query));
  });

  recentRecords = computed(() => this.records().slice(0, 5));
  selectedTopicStat = computed(() => {
    const topic = this.selectedTopic();
    if (!topic) return null;
    return this.filteredTopicStats().find((s) => s.topic === topic) ?? null;
  });

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.examService.getHistory().subscribe((data) => {
      this.records.set(data);
      const topics = this.topicStats();
      if (topics.length > 0) {
        this.selectedTopic.set(topics[0].topic);
      }
      setTimeout(() => this.renderCharts(), 0);
    });
  }

  ngOnDestroy(): void {
    this.charts.forEach((c) => c.destroy());
  }

  viewRecord(id: string): void {
    this.router.navigate(['/history', id]);
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString();
  }

  formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  }

  onTopicSearchInput(value: string): void {
    this.topicSearch.set(value);
    this.topicDropdownOpen.set(true);
    const filtered = this.filteredTopicStats();
    if (filtered.length > 0 && !filtered.some((t) => t.topic === this.selectedTopic())) {
      this.selectedTopic.set(filtered[0].topic);
    }
    if (filtered.length === 0) {
      this.selectedTopic.set('');
    }
  }

  selectTopic(topic: string): void {
    this.selectedTopic.set(topic);
    this.topicSearch.set(topic);
    this.topicDropdownOpen.set(false);
  }

  onTopicSearchFocus(): void {
    this.topicDropdownOpen.set(true);
  }

  closeTopicDropdown(): void {
    this.topicDropdownOpen.set(false);
  }

  private renderCharts(): void {
    this.charts.forEach((c) => c.destroy());
    this.charts = [];
    if (this.records().length === 0) return;

    this.renderScoreTrend();
    this.renderModeBreakdown();
    this.renderScoreDistribution();
  }

  private renderScoreTrend(): void {
    const canvas = document.getElementById('scoreTrendChart') as HTMLCanvasElement;
    if (!canvas) return;

    const sorted = [...this.records()].reverse();
    const labels = sorted.map((r, i) => `#${i + 1}`);
    const data = sorted.map((r) => r.score);

    this.charts.push(
      new Chart(canvas, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Score %',
              data,
              borderColor: '#4361ee',
              backgroundColor: 'rgba(67, 97, 238, 0.08)',
              fill: true,
              tension: 0.35,
              pointRadius: 4,
              pointBackgroundColor: '#4361ee',
              borderWidth: 2,
            },
            {
              label: 'Pass Threshold',
              data: sorted.map(() => 72),
              borderColor: '#e0e0e0',
              borderDash: [6, 4],
              borderWidth: 1.5,
              pointRadius: 0,
              fill: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` }, grid: { color: '#f0f0f0' } },
            x: { grid: { display: false } },
          },
        },
      }),
    );
  }

  private renderModeBreakdown(): void {
    const canvas = document.getElementById('modeChart') as HTMLCanvasElement;
    if (!canvas) return;

    const examCount = this.examCount();
    const practiceCount = this.practiceCount();
    if (examCount === 0 && practiceCount === 0) return;

    this.charts.push(
      new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels: ['Exam', 'Practice'],
          datasets: [
            {
              data: [examCount, practiceCount],
              backgroundColor: ['#4361ee', '#0a7'],
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
            legend: { position: 'bottom', labels: { padding: 16, usePointStyle: true, pointStyle: 'circle' } },
          },
        },
      }),
    );
  }

  private renderScoreDistribution(): void {
    const canvas = document.getElementById('distChart') as HTMLCanvasElement;
    if (!canvas) return;

    const buckets = Array(10).fill(0);
    for (const r of this.records()) {
      const idx = Math.min(Math.floor(r.score / 10), 9);
      buckets[idx]++;
    }
    const labels = buckets.map((_, i) => `${i * 10}-${i * 10 + 10}%`);

    this.charts.push(
      new Chart(canvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: 'Attempts',
              data: buckets,
              backgroundColor: buckets.map((_, i) => (i >= 8 ? '#0a7' : i >= 5 ? '#4361ee' : '#e8e8e8')),
              borderRadius: 4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: '#f0f0f0' } },
            x: { grid: { display: false } },
          },
        },
      }),
    );
  }
}
