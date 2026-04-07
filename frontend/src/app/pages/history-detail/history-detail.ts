import { Component, OnInit, signal, computed } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ExamService, ExamResult, QuestionResult } from '../../services/exam.service';

@Component({
  selector: 'app-history-detail',
  imports: [],
  templateUrl: './history-detail.html',
  styleUrl: './history-detail.scss',
})
export class HistoryDetailPage implements OnInit {
  result = signal<ExamResult | null>(null);

  formattedTime = computed(() => {
    const s = this.result()?.time_spent_seconds ?? 0;
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins}m ${secs}s`;
  });

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.examService.getHistoryRecord(id).subscribe((r) => this.result.set(r));
  }

  goBack(): void {
    this.router.navigate(['/history']);
  }

  formatAnswer(ans: string | string[] | null): string {
    if (ans === null || ans === undefined) return '—';
    if (Array.isArray(ans)) return ans.length ? ans.join(', ') : '—';
    return ans || '—';
  }

  isUserPick(q: QuestionResult, opt: string): boolean {
    const letter = opt.charAt(0);
    if (Array.isArray(q.user_answer)) return q.user_answer.includes(letter);
    if (q.user_answer && q.user_answer.length > 1) return q.user_answer === opt;
    return q.user_answer === letter;
  }

  isCorrectOpt(q: QuestionResult, opt: string): boolean {
    const letter = opt.charAt(0);
    if (Array.isArray(q.correct_answer)) return q.correct_answer.includes(letter);
    if (q.correct_answer && q.correct_answer.length > 1) return q.correct_answer === opt;
    return q.correct_answer === letter;
  }
}
