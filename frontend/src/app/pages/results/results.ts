import { Component, OnInit, signal, computed } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { QuestionSectionsComponent } from '../../components/question-sections/question-sections';
import {
  ExamService,
  ExamResult,
  QuestionResult,
  AnswerValue,
  countQuestionTypes,
  classifyQuestionType,
  formatAnswerForDisplay,
} from '../../services/exam.service';

@Component({
  selector: 'app-results',
  imports: [QuestionSectionsComponent],
  templateUrl: './results.html',
  styleUrl: './results.scss',
})
export class ResultsPage implements OnInit {
  result = signal<ExamResult | null>(null);

  formattedTime = computed(() => {
    const s = this.result()?.time_spent_seconds ?? 0;
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins}m ${secs}s`;
  });

  typeCounts = computed(() => countQuestionTypes(this.result()?.results ?? []));

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.examService.getHistoryRecord(id).subscribe((r) => this.result.set(r));
  }

  goHome(): void {
    this.router.navigate(['/exams']);
  }

  retake(): void {
    const r = this.result();
    if (r) this.router.navigate(['/exam', r.exam_id]);
  }

  formatAnswer(q: QuestionResult, ans: AnswerValue | null | undefined): string {
    return formatAnswerForDisplay(q, ans);
  }

  /** Only MCQ/SATA render a letter-based option list. */
  showOptionList(q: QuestionResult): boolean {
    const kind = classifyQuestionType(q);
    return (kind === 'MCQ' || kind === 'SATA') && Array.isArray(q.options) && q.options.length > 0;
  }

  optionList(q: QuestionResult): string[] {
    return Array.isArray(q.options) ? q.options : [];
  }

  isAdvanced(q: QuestionResult): boolean {
    const kind = classifyQuestionType(q);
    return kind !== 'MCQ' && kind !== 'SATA' && kind !== 'FIB';
  }

  isUserPick(q: QuestionResult, opt: string): boolean {
    const letter = opt.charAt(0);
    if (Array.isArray(q.user_answer)) return (q.user_answer as string[]).map(String).includes(letter);
    if (!q.user_answer) return false;
    const letters = String(q.user_answer).split(',').map((s) => s.trim());
    return letters.includes(letter);
  }

  isCorrectOpt(q: QuestionResult, opt: string): boolean {
    const letter = opt.charAt(0);
    if (Array.isArray(q.correct_answer)) return (q.correct_answer as string[]).map(String).includes(letter);
    const letters = String(q.correct_answer).split(',').map((s) => s.trim());
    return letters.includes(letter);
  }
}
