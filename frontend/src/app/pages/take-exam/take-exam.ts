import { Component, OnInit, OnDestroy, signal, computed } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService, Question, AnswerSubmission } from '../../services/exam.service';

@Component({
  selector: 'app-take-exam',
  imports: [FormsModule],
  templateUrl: './take-exam.html',
  styleUrl: './take-exam.scss',
})
export class TakeExamPage implements OnInit, OnDestroy {
  examTitle = signal('');
  questions = signal<Question[]>([]);
  answers = signal<Map<number, string | string[]>>(new Map());
  flagged = signal<Set<number>>(new Set());
  submitting = signal(false);
  showNav = signal(false);

  mode = signal<'exam' | 'practice'>('exam');
  remainingSeconds = signal(180 * 60);
  currentPage = signal(0);
  readonly questionsPerPage = 20;

  revealed = signal<Set<number>>(new Set());
  fibConfirmed = signal<Set<number>>(new Set());
  fibUserMarked = signal<Map<number, boolean>>(new Map());

  private timerInterval: ReturnType<typeof setInterval> | null = null;
  private examId = '';

  totalQuestions = computed(() => this.questions().length);
  answeredCount = computed(() => this.answers().size);
  progress = computed(() =>
    this.totalQuestions() > 0 ? Math.round((this.answeredCount() / this.totalQuestions()) * 100) : 0,
  );

  totalPages = computed(() => Math.ceil(this.totalQuestions() / this.questionsPerPage));
  pageQuestions = computed(() => {
    const start = this.currentPage() * this.questionsPerPage;
    return this.questions().slice(start, start + this.questionsPerPage);
  });
  pageStartNum = computed(() => this.currentPage() * this.questionsPerPage + 1);
  pageEndNum = computed(() => Math.min((this.currentPage() + 1) * this.questionsPerPage, this.totalQuestions()));

  formattedTime = computed(() => {
    const s = this.remainingSeconds();
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${pad(hrs)}:${pad(mins)}:${pad(secs)}`;
  });

  timerWarning = computed(() => this.remainingSeconds() <= 300 && this.remainingSeconds() > 60);
  timerDanger = computed(() => this.remainingSeconds() <= 60);

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    this.examId = this.route.snapshot.paramMap.get('id')!;
    const modeParam = this.route.snapshot.queryParamMap.get('mode');
    if (modeParam === 'practice') this.mode.set('practice');

    this.examService.getExam(this.examId, true).subscribe((exam) => {
      this.examTitle.set(exam.title);
      this.questions.set(this.shuffle(exam.questions));
    });

    this.timerInterval = setInterval(() => {
      const remaining = this.remainingSeconds();
      if (remaining <= 1) {
        this.remainingSeconds.set(0);
        if (this.timerInterval) clearInterval(this.timerInterval);
        if (this.mode() === 'exam' && !this.submitting()) this.submit();
        return;
      }
      this.remainingSeconds.update((v) => v - 1);
    }, 1000);
  }

  ngOnDestroy(): void {
    if (this.timerInterval) clearInterval(this.timerInterval);
  }

  private shuffle<T>(arr: T[]): T[] {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  // ── Page Navigation ─────────────────────────────────────────

  goTo(index: number): void {
    const page = Math.floor(index / this.questionsPerPage);
    this.currentPage.set(page);
    this.showNav.set(false);
  }

  prevPage(): void {
    if (this.currentPage() > 0) {
      this.currentPage.update((p) => p - 1);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  nextPage(): void {
    if (this.currentPage() < this.totalPages() - 1) {
      this.currentPage.update((p) => p + 1);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  toggleNav(): void {
    this.showNav.update((v) => !v);
  }

  isOnCurrentPage(index: number): boolean {
    return Math.floor(index / this.questionsPerPage) === this.currentPage();
  }

  // ── Answering ───────────────────────────────────────────────

  isTextInput(q: Question): boolean {
    return !q.options || q.options.length === 0 || q.type === 'FIB' || q.type === 'Fill-in-the-blank';
  }

  selectMCQ(qNum: number, option: string): void {
    if (this.isRevealed(qNum)) return;
    const letter = option.charAt(0);
    const map = new Map(this.answers());
    map.set(qNum, letter);
    this.answers.set(map);

    if (this.mode() === 'practice') {
      this.revealQuestion(qNum);
    }
  }

  toggleSATA(qNum: number, option: string): void {
    if (this.isRevealed(qNum)) return;
    const letter = option.charAt(0);
    const map = new Map(this.answers());
    const current = (map.get(qNum) as string[]) || [];
    const idx = current.indexOf(letter);
    const updated = idx >= 0 ? current.filter((c) => c !== letter) : [...current, letter];
    map.set(qNum, updated);
    this.answers.set(map);
  }

  setTextAnswer(qNum: number, value: string): void {
    const map = new Map(this.answers());
    map.set(qNum, value);
    this.answers.set(map);
  }

  getAnswer(qNum: number): string | string[] | undefined {
    return this.answers().get(qNum);
  }

  isSataSelected(qNum: number, option: string): boolean {
    const ans = this.answers().get(qNum);
    return Array.isArray(ans) && ans.includes(option.charAt(0));
  }

  isSelected(qNum: number, option: string): boolean {
    return this.answers().get(qNum) === option.charAt(0);
  }

  // ── Practice Mode / Reveal ──────────────────────────────────

  revealQuestion(qNum: number): void {
    const s = new Set(this.revealed());
    s.add(qNum);
    this.revealed.set(s);
  }

  isRevealed(qNum: number): boolean {
    return this.revealed().has(qNum);
  }

  checkSATAAnswer(qNum: number): void {
    this.revealQuestion(qNum);
  }

  isCorrectOption(q: Question, option: string): boolean {
    const letter = option.charAt(0);
    if (Array.isArray(q.answer)) return q.answer.includes(letter);
    return q.answer === letter;
  }

  isQuestionCorrect(q: Question): boolean {
    if (this.isTextInput(q)) {
      return this.getFibMark(q.number) === true;
    }
    if (!q.answer) return false;
    const answer = this.getAnswer(q.number);
    if (q.type === 'SATA') {
      const expected: Set<string> = new Set(Array.isArray(q.answer) ? q.answer : [q.answer]);
      const userArr = Array.isArray(answer) ? answer : [];
      const userSet: Set<string> = new Set(userArr);
      return expected.size === userSet.size && [...expected].every((e) => userSet.has(e));
    }
    return answer === (Array.isArray(q.answer) ? q.answer[0] : q.answer);
  }

  // ── FIB Confirm & Self-Grade ────────────────────────────────

  confirmFib(qNum: number): void {
    const s = new Set(this.fibConfirmed());
    s.add(qNum);
    this.fibConfirmed.set(s);
    this.revealQuestion(qNum);
  }

  isFibConfirmed(qNum: number): boolean {
    return this.fibConfirmed().has(qNum);
  }

  markFib(qNum: number, correct: boolean): void {
    const m = new Map(this.fibUserMarked());
    m.set(qNum, correct);
    this.fibUserMarked.set(m);
  }

  getFibMark(qNum: number): boolean | undefined {
    return this.fibUserMarked().get(qNum);
  }

  // ── Flagging ────────────────────────────────────────────────

  toggleFlag(qNum: number): void {
    const s = new Set(this.flagged());
    if (s.has(qNum)) s.delete(qNum);
    else s.add(qNum);
    this.flagged.set(s);
  }

  isFlagged(qNum: number): boolean {
    return this.flagged().has(qNum);
  }

  isAnswered(qNum: number): boolean {
    const ans = this.answers().get(qNum);
    if (ans === undefined) return false;
    if (Array.isArray(ans)) return ans.length > 0;
    return ans !== '';
  }

  // ── Submit ──────────────────────────────────────────────────

  submit(): void {
    if (this.submitting()) return;

    const unanswered = this.totalQuestions() - this.answeredCount();
    if (unanswered > 0) {
      const confirmed = confirm(`You have ${unanswered} unanswered question(s). Submit anyway?`);
      if (!confirmed) return;
    }

    this.submitting.set(true);
    const timeSpent = 180 * 60 - this.remainingSeconds();
    const subs: AnswerSubmission[] = this.questions().map((q) => ({
      question_number: q.number,
      answer: this.answers().get(q.number) ?? (q.type === 'SATA' ? [] : ''),
    }));

    this.examService
      .submitExam({
        exam_id: this.examId,
        answers: subs,
        time_spent_seconds: timeSpent,
        mode: this.mode(),
      })
      .subscribe({
        next: (result) => {
          this.submitting.set(false);
          this.router.navigate(['/results', result.id]);
        },
        error: () => {
          this.submitting.set(false);
          alert('Submission failed. Please try again.');
        },
      });
  }
}
