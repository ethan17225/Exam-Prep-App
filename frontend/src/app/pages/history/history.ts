import { Component, OnInit, signal, computed } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService, ExamResult } from '../../services/exam.service';

@Component({
  selector: 'app-history',
  imports: [FormsModule],
  templateUrl: './history.html',
  styleUrl: './history.scss',
})
export class HistoryPage implements OnInit {
  records = signal<ExamResult[]>([]);
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
    this.examService.getHistory().subscribe((data) => this.records.set(data));
  }

  view(id: string): void {
    this.router.navigate(['/history', id]);
  }

  remove(id: string, event: Event): void {
    event.stopPropagation();
    this.examService.deleteHistoryRecord(id).subscribe(() => this.load());
  }

  formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString();
  }
}
