import { Component, OnInit, signal, computed } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService, InProgressExam } from '../../services/exam.service';

@Component({
  selector: 'app-in-progress',
  imports: [FormsModule],
  templateUrl: './in-progress.html',
  styleUrl: './in-progress.scss',
})
export class InProgressPage implements OnInit {
  records = signal<InProgressExam[]>([]);
  searchQuery = signal('');

  filteredRecords = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    if (!query) return this.records();
    return this.records().filter((r) => r.exam_title.toLowerCase().includes(query));
  });

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.examService.listInProgress().subscribe((data) => this.records.set(data));
  }

  resume(record: InProgressExam): void {
    this.router.navigate(['/exam', record.exam_id], {
      queryParams: { mode: record.mode, resume: record.id },
    });
  }

  remove(id: string, event: Event): void {
    event.stopPropagation();
    if (!confirm('Discard this in-progress exam?')) return;
    this.examService.deleteInProgress(id).subscribe(() => this.load());
  }

  formatTime(seconds: number): string {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hrs > 0) return `${hrs}h ${mins}m remaining`;
    return `${mins}m remaining`;
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString();
  }

  progressPercent(record: InProgressExam): number {
    if (record.total_questions === 0) return 0;
    return Math.round((record.answered_count / record.total_questions) * 100);
  }
}
