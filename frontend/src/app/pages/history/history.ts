import { Component, OnInit, signal, computed } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  ExamService,
  ExamResultSummary,
  formatDate,
  formatDuration,
} from '../../services/exam.service';

@Component({
  selector: 'app-history',
  imports: [FormsModule],
  templateUrl: './history.html',
  styleUrl: './history.scss',
})
export class HistoryPage implements OnInit {
  records = signal<ExamResultSummary[]>([]);
  searchQuery = signal('');
  loading = signal(true);
  loadError = signal('');
  deleteError = signal<Record<string, string>>({});

  filteredRecords = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    if (!query) return this.records();
    return this.records().filter((r) => r.exam_title.toLowerCase().includes(query));
  });

  readonly formatDate = formatDate;
  readonly formatDuration = formatDuration;

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.getHistory().subscribe({
      next: (data) => {
        this.records.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load test history.');
      },
    });
  }

  view(id: string): void {
    this.router.navigate(['/history', id]);
  }

  remove(id: string, event: Event): void {
    event.stopPropagation();
    this.examService.deleteHistoryRecord(id).subscribe({
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
