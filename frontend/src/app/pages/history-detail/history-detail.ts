import { Component, OnInit, signal, computed } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AnswerReviewComponent } from '../../components/answer-review/answer-review';
import {
  ExamService,
  ExamResult,
  QuestionResult,
  classifyQuestionType,
  countQuestionTypes,
  formatDuration,
} from '../../services/exam.service';

@Component({
  selector: 'app-history-detail',
  imports: [AnswerReviewComponent],
  templateUrl: './history-detail.html',
  styleUrl: './history-detail.scss',
})
export class HistoryDetailPage implements OnInit {
  result = signal<ExamResult | null>(null);
  loading = signal(true);
  loadError = signal('');
  showWrongOnly = signal(false);
  selectedType = signal<'all' | 'MCQ' | 'SATA' | 'FIB' | 'OTHER'>('all');

  formattedTime = computed(() => formatDuration(this.result()?.time_spent_seconds ?? 0));
  typeCounts = computed(() => countQuestionTypes(this.result()?.results ?? []));

  filteredResults = computed(() => {
    let results = this.result()?.results ?? [];
    if (this.showWrongOnly()) {
      results = results.filter((q) => !q.is_correct);
    }
    if (this.selectedType() !== 'all') {
      const desired = this.selectedType();
      results = results.filter((q) => this.getQuestionTypeGroup(q) === desired);
    }
    return results;
  });

  private recordId = '';

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    this.recordId = this.route.snapshot.paramMap.get('id')!;
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.getHistoryRecord(this.recordId).subscribe({
      next: (r) => {
        this.result.set(r);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load this record.');
      },
    });
  }

  goBack(): void {
    this.router.navigate(['/history']);
  }

  toggleWrongOnly(): void {
    this.showWrongOnly.update((v) => !v);
  }

  setTypeFilter(value: 'all' | 'MCQ' | 'SATA' | 'FIB' | 'OTHER'): void {
    this.selectedType.set(value);
  }

  getQuestionTypeGroup(q: QuestionResult): 'MCQ' | 'SATA' | 'FIB' | 'OTHER' {
    const kind = classifyQuestionType(q);
    return kind === 'MCQ' || kind === 'SATA' || kind === 'FIB' ? kind : 'OTHER';
  }
}
