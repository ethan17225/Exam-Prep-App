import { Component, OnInit, signal, computed } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  ExamService,
  InProgressExam,
  formatDate,
  formatDuration,
  progressPercent,
} from '../../services/exam.service';

@Component({
  selector: 'app-in-progress',
  imports: [FormsModule],
  templateUrl: './in-progress.html',
  styleUrl: './in-progress.scss',
})
export class InProgressPage implements OnInit {
  records = signal<InProgressExam[]>([]);
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
  readonly progressPercent = progressPercent;

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
    this.examService.listInProgress().subscribe({
      next: (data) => {
        this.records.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load in-progress exams.');
      },
    });
  }

  resume(record: InProgressExam): void {
    this.router.navigate(['/exam', record.exam_id], {
      queryParams: { mode: record.mode, resume: record.id },
    });
  }

  remove(id: string, event: Event): void {
    event.stopPropagation();
    if (!confirm('Discard this in-progress exam?')) return;
    this.examService.deleteInProgress(id).subscribe({
      next: () => this.load(),
      error: (err) => {
        this.deleteError.set({
          ...this.deleteError(),
          [id]: err?.error?.detail || 'Discard failed.',
        });
      },
    });
  }
}
