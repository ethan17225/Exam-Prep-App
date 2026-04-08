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
  showWrongOnly = signal(false);
  selectedType = signal<'all' | 'MCQ' | 'SATA' | 'FIB'>('all');

  formattedTime = computed(() => {
    const s = this.result()?.time_spent_seconds ?? 0;
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins}m ${secs}s`;
  });

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

  toggleWrongOnly(): void {
    this.showWrongOnly.update((v) => !v);
  }

  setTypeFilter(value: 'all' | 'MCQ' | 'SATA' | 'FIB'): void {
    this.selectedType.set(value);
  }

  formatAnswer(ans: string | string[] | null): string {
    if (ans === null || ans === undefined) return '—';
    if (Array.isArray(ans)) return ans.length ? ans.join(', ') : '—';
    return ans || '—';
  }

  /** First answer letter (A–Z) from an option line, e.g. "A. Text" or "  B) ..." */
  private optionLetter(opt: string): string {
    const t = opt.trim();
    const m = t.match(/^([A-Z])\s*[\.\)]/i) ?? t.match(/^([A-Z])\b/i);
    return (m ? m[1] : t.charAt(0)).toUpperCase();
  }

  /** Letters the user selected (handles arrays, comma strings, and single letter). */
  private userAnswerLetters(q: QuestionResult): Set<string> {
    const ua = q.user_answer;
    if (ua === null || ua === undefined) return new Set();
    if (Array.isArray(ua)) {
      return new Set(ua.map((x) => String(x).trim().toUpperCase().slice(0, 1)).filter(Boolean));
    }
    const s = String(ua).trim();
    if (s.includes(',')) {
      return new Set(
        s
          .split(',')
          .map((x) => x.trim().toUpperCase().slice(0, 1))
          .filter(Boolean),
      );
    }
    return new Set([s.toUpperCase().slice(0, 1)]);
  }

  /** Letters that are correct for this question. */
  private correctAnswerLetters(q: QuestionResult): Set<string> {
    const ca = q.correct_answer;
    if (Array.isArray(ca)) {
      return new Set(ca.map((x) => String(x).trim().toUpperCase().slice(0, 1)).filter(Boolean));
    }
    const s = String(ca ?? '').trim();
    if (s.includes(',')) {
      return new Set(
        s
          .split(',')
          .map((x) => x.trim().toUpperCase().slice(0, 1))
          .filter(Boolean),
      );
    }
    return new Set([s.toUpperCase().slice(0, 1)].filter(Boolean));
  }

  isUserPick(q: QuestionResult, opt: string): boolean {
    const letter = this.optionLetter(opt);
    const picks = this.userAnswerLetters(q);
    return picks.has(letter);
  }

  isCorrectOpt(q: QuestionResult, opt: string): boolean {
    const letter = this.optionLetter(opt);
    return this.correctAnswerLetters(q).has(letter);
  }

  isSata(q: QuestionResult): boolean {
    return (q.type ?? '').trim().toUpperCase() === 'SATA';
  }

  getQuestionTypeGroup(q: QuestionResult): 'MCQ' | 'SATA' | 'FIB' {
    if (q.type === 'SATA') return 'SATA';
    if (q.type === 'FIB' || q.type === 'Fill-in-the-blank' || !q.options || q.options.length === 0) return 'FIB';
    return 'MCQ';
  }
}
