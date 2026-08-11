import { Component, OnInit, signal, computed } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AnswerReviewComponent } from '../../components/answer-review/answer-review';
import {
  ExamService,
  ExamResult,
  countQuestionTypes,
  formatDuration,
} from '../../services/exam.service';

@Component({
  selector: 'app-results',
  imports: [AnswerReviewComponent],
  templateUrl: './results.html',
  styleUrl: './results.scss',
})
export class ResultsPage implements OnInit {
  result = signal<ExamResult | null>(null);
  loading = signal(true);
  loadError = signal('');

  formattedTime = computed(() => formatDuration(this.result()?.time_spent_seconds ?? 0));
  typeCounts = computed(() => countQuestionTypes(this.result()?.results ?? []));

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
        this.loadError.set(err?.error?.detail || 'Failed to load the results.');
      },
    });
  }

  goHome(): void {
    this.router.navigate(['/exams']);
  }

  retake(): void {
    const r = this.result();
    if (r) this.router.navigate(['/exam', r.exam_id]);
  }
}
