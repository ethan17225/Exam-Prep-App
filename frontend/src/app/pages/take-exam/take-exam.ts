import { Component, OnInit, OnDestroy, signal, computed } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { QuestionSectionsComponent } from '../../components/question-sections/question-sections';
import {
  ExamService,
  Question,
  AnswerSubmission,
  AnswerValue,
  InProgressExam,
  QuestionKind,
  BowtieCategory,
  ClozeBlank,
  HotspotRegion,
  countQuestionTypes,
  classifyQuestionType,
  formatAnswerForDisplay,
  matrixRows,
  matrixColumns,
  clozeBlanks,
  bowtieCategories,
  highlightTokens,
  hotspotRegions,
  rankingItems,
} from '../../services/exam.service';

@Component({
  selector: 'app-take-exam',
  imports: [FormsModule, QuestionSectionsComponent],
  templateUrl: './take-exam.html',
  styleUrl: './take-exam.scss',
})
export class TakeExamPage implements OnInit, OnDestroy {
  examTitle = signal('');
  questions = signal<Question[]>([]);
  answers = signal<Map<number, AnswerValue>>(new Map());
  flagged = signal<Set<number>>(new Set());
  submitting = signal(false);
  showNav = signal(false);
  autoSaveStatus = signal<'idle' | 'saving' | 'saved'>('idle');

  mode = signal<'exam' | 'practice'>('exam');
  timeLimitSeconds = signal(180 * 60);
  remainingSeconds = signal(180 * 60);
  currentPage = signal(0);
  readonly questionsPerPage = 20;

  revealed = signal<Set<number>>(new Set());
  fibConfirmed = signal<Set<number>>(new Set());
  fibUserMarked = signal<Map<number, boolean>>(new Map());

  private timerInterval: ReturnType<typeof setInterval> | null = null;
  private autoSaveTimeout: ReturnType<typeof setTimeout> | null = null;
  private examId = '';
  private resumeId: string | null = null;
  private selectedQuestionCount: number | null = null;

  totalQuestions = computed(() => this.questions().length);
  typeCounts = computed(() => countQuestionTypes(this.questions()));
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
    this.resumeId = this.route.snapshot.queryParamMap.get('resume');
    const countParam = Number(this.route.snapshot.queryParamMap.get('count'));
    if (Number.isFinite(countParam) && countParam > 0) {
      this.selectedQuestionCount = Math.floor(countParam);
    }

    this.examService.getExam(this.examId, true).subscribe((exam) => {
      this.examTitle.set(exam.title);
      
      const limit = exam.time_limit_minutes ? exam.time_limit_minutes * 60 : 180 * 60;
      this.timeLimitSeconds.set(limit);

      if (this.resumeId) {
        this.examService.getInProgress(this.resumeId).subscribe((saved) => {
          this.restoreProgress(exam.questions, saved);
          this.startTimer();
        });
      } else {
        const shuffled = this.shuffle(exam.questions);
        const takeCount = this.selectedQuestionCount
          ? Math.min(Math.max(this.selectedQuestionCount, 1), shuffled.length)
          : shuffled.length;
        this.questions.set(shuffled.slice(0, takeCount));
        this.remainingSeconds.set(limit);
        this.startTimer();
        this.persistProgress();
      }
    });
  }

  private startTimer(): void {
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

  private restoreProgress(allQuestions: Question[], saved: InProgressExam): void {
    const questionMap = new Map(allQuestions.map((q) => [q.number, q]));
    const ordered = saved.question_order
      .map((num) => questionMap.get(num))
      .filter((q): q is Question => !!q);
    this.questions.set(ordered);

    const restoredAnswers = new Map<number, AnswerValue>();
    for (const [key, val] of Object.entries(saved.answers)) {
      restoredAnswers.set(Number(key), val);
    }
    this.answers.set(restoredAnswers);
    this.flagged.set(new Set(saved.flagged));
    this.remainingSeconds.set(saved.remaining_seconds);
    this.currentPage.set(saved.current_page);
  }

  ngOnDestroy(): void {
    if (this.timerInterval) clearInterval(this.timerInterval);
    if (this.autoSaveTimeout) clearTimeout(this.autoSaveTimeout);
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

  kind(q: Question): QuestionKind {
    return classifyQuestionType(q);
  }

  isAdvanced(q: Question): boolean {
    const k = this.kind(q);
    return k !== 'MCQ' && k !== 'SATA' && k !== 'FIB';
  }

  isTextInput(q: Question): boolean {
    return this.kind(q) === 'FIB';
  }

  mcqOptions(q: Question): string[] {
    return Array.isArray(q.options) ? q.options : [];
  }

  private setAnswer(qNum: number, value: AnswerValue): void {
    const map = new Map(this.answers());
    map.set(qNum, value);
    this.answers.set(map);
    this.scheduleAutoSave();
  }

  selectMCQ(qNum: number, option: string): void {
    if (this.isRevealed(qNum)) return;
    const letter = option.charAt(0);
    const map = new Map(this.answers());
    map.set(qNum, letter);
    this.answers.set(map);
    this.scheduleAutoSave();

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
    this.scheduleAutoSave();
  }

  setTextAnswer(qNum: number, value: string): void {
    this.setAnswer(qNum, value);
  }

  getAnswer(qNum: number): AnswerValue | undefined {
    return this.answers().get(qNum);
  }

  // ── MATRIX ──────────────────────────────────────────────────

  matrixRows(q: Question): string[] {
    return matrixRows(q);
  }

  matrixCols(q: Question): string[] {
    return matrixColumns(q);
  }

  private matrixAnswer(qNum: number): Record<string, string[]> {
    const ans = this.answers().get(qNum);
    return ans && typeof ans === 'object' && !Array.isArray(ans) ? (ans as Record<string, string[]>) : {};
  }

  toggleMatrix(qNum: number, rowIdx: number, col: string): void {
    if (this.isRevealed(qNum)) return;
    const current = { ...this.matrixAnswer(qNum) };
    const key = String(rowIdx);
    const selections = [...(current[key] ?? [])];
    const idx = selections.indexOf(col);
    if (idx >= 0) selections.splice(idx, 1);
    else selections.push(col);
    if (selections.length) current[key] = selections;
    else delete current[key];
    this.setAnswer(qNum, current);
  }

  isMatrixChecked(qNum: number, rowIdx: number, col: string): boolean {
    return (this.matrixAnswer(qNum)[String(rowIdx)] ?? []).includes(col);
  }

  isMatrixExpected(q: Question, rowIdx: number, col: string): boolean {
    const expected = q.answer;
    if (!expected || typeof expected !== 'object' || Array.isArray(expected)) return false;
    return ((expected as Record<string, string[]>)[String(rowIdx)] ?? []).includes(col);
  }

  // ── CLOZE ───────────────────────────────────────────────────

  clozeBlanks(q: Question): ClozeBlank[] {
    return clozeBlanks(q);
  }

  private clozeAnswer(qNum: number, blankCount: number): string[] {
    const ans = this.answers().get(qNum);
    const list = Array.isArray(ans) ? [...(ans as string[])] : [];
    while (list.length < blankCount) list.push('');
    return list;
  }

  setClozeAnswer(q: Question, blankIdx: number, value: string): void {
    if (this.isRevealed(q.number)) return;
    const list = this.clozeAnswer(q.number, this.clozeBlanks(q).length);
    list[blankIdx] = value;
    this.setAnswer(q.number, list);
  }

  getClozeAnswer(qNum: number, blankIdx: number): string {
    const ans = this.answers().get(qNum);
    return Array.isArray(ans) ? String((ans as string[])[blankIdx] ?? '') : '';
  }

  clozeExpected(q: Question, blankIdx: number): string {
    return Array.isArray(q.answer) ? String((q.answer as string[])[blankIdx] ?? '') : '';
  }

  isClozeBlankCorrect(q: Question, blankIdx: number): boolean {
    const user = this.getClozeAnswer(q.number, blankIdx).trim().toLowerCase();
    return !!user && user === this.clozeExpected(q, blankIdx).trim().toLowerCase();
  }

  // ── BOWTIE ──────────────────────────────────────────────────

  bowtieCategories(q: Question): BowtieCategory[] {
    return bowtieCategories(q);
  }

  private bowtieAnswer(qNum: number): Record<string, string[]> {
    const ans = this.answers().get(qNum);
    return ans && typeof ans === 'object' && !Array.isArray(ans) ? (ans as Record<string, string[]>) : {};
  }

  toggleBowtie(qNum: number, cat: BowtieCategory, choice: string): void {
    if (this.isRevealed(qNum)) return;
    const current = { ...this.bowtieAnswer(qNum) };
    const selections = [...(current[cat.name] ?? [])];
    const idx = selections.indexOf(choice);
    if (idx >= 0) {
      selections.splice(idx, 1);
    } else {
      if (cat.count && selections.length >= cat.count) {
        if (cat.count === 1) selections.length = 0;
        else return;
      }
      selections.push(choice);
    }
    if (selections.length) current[cat.name] = selections;
    else delete current[cat.name];
    this.setAnswer(qNum, current);
  }

  isBowtieSelected(qNum: number, catName: string, choice: string): boolean {
    return (this.bowtieAnswer(qNum)[catName] ?? []).includes(choice);
  }

  isBowtieExpected(q: Question, catName: string, choice: string): boolean {
    const expected = q.answer;
    if (!expected || typeof expected !== 'object' || Array.isArray(expected)) return false;
    return ((expected as Record<string, string[]>)[catName] ?? []).includes(choice);
  }

  bowtieSelectedCount(qNum: number, catName: string): number {
    return (this.bowtieAnswer(qNum)[catName] ?? []).length;
  }

  // ── RANKING ─────────────────────────────────────────────────

  rankOrder(q: Question): string[] {
    const ans = this.answers().get(q.number);
    if (Array.isArray(ans) && ans.length > 0) return ans as string[];
    return rankingItems(q);
  }

  moveRank(q: Question, index: number, delta: number): void {
    if (this.isRevealed(q.number)) return;
    const order = [...this.rankOrder(q)];
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    this.setAnswer(q.number, order);
  }

  confirmRankOrder(q: Question): void {
    if (this.isRevealed(q.number)) return;
    this.setAnswer(q.number, [...this.rankOrder(q)]);
  }

  isRankConfirmed(qNum: number): boolean {
    const ans = this.answers().get(qNum);
    return Array.isArray(ans) && ans.length > 0;
  }

  isRankItemCorrect(q: Question, index: number): boolean {
    const expected = Array.isArray(q.answer) ? (q.answer as string[]).map(String) : [];
    const current = this.rankOrder(q);
    return String(current[index] ?? '').trim() === String(expected[index] ?? '').trim();
  }

  // ── HIGHLIGHT ───────────────────────────────────────────────

  highlightTokens(q: Question): string[] {
    return highlightTokens(q);
  }

  private highlightAnswer(qNum: number): number[] {
    const ans = this.answers().get(qNum);
    return Array.isArray(ans) ? (ans as number[]).map(Number) : [];
  }

  toggleHighlight(qNum: number, tokenIdx: number): void {
    if (this.isRevealed(qNum)) return;
    const current = [...this.highlightAnswer(qNum)];
    const idx = current.indexOf(tokenIdx);
    if (idx >= 0) current.splice(idx, 1);
    else current.push(tokenIdx);
    current.sort((a, b) => a - b);
    this.setAnswer(qNum, current);
  }

  isHighlighted(qNum: number, tokenIdx: number): boolean {
    return this.highlightAnswer(qNum).includes(tokenIdx);
  }

  isHighlightExpected(q: Question, tokenIdx: number): boolean {
    return Array.isArray(q.answer) && (q.answer as number[]).map(Number).includes(tokenIdx);
  }

  // ── HOTSPOT ─────────────────────────────────────────────────

  hotspotRegions(q: Question): HotspotRegion[] {
    return hotspotRegions(q);
  }

  selectHotspot(qNum: number, regionId: string): void {
    if (this.isRevealed(qNum)) return;
    this.setAnswer(qNum, regionId);
  }

  isHotspotSelected(qNum: number, regionId: string): boolean {
    return this.answers().get(qNum) === regionId;
  }

  isHotspotExpected(q: Question, regionId: string): boolean {
    return String(q.answer ?? '') === regionId;
  }

  hotspotSelectedLabel(q: Question): string {
    const ans = this.answers().get(q.number);
    if (!ans || typeof ans !== 'string') return '';
    return this.hotspotRegions(q).find((r) => r.id === ans)?.label ?? '';
  }

  isSataSelected(qNum: number, option: string): boolean {
    const ans = this.answers().get(qNum);
    return Array.isArray(ans) && (ans as string[]).includes(option.charAt(0));
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
    if (Array.isArray(q.answer)) return (q.answer as string[]).map(String).includes(letter);
    const letters = String(q.answer ?? '').split(',').map((s) => s.trim());
    return letters.includes(letter);
  }

  correctAnswerText(q: Question): string {
    return formatAnswerForDisplay(q, q.answer ?? null);
  }

  isQuestionCorrect(q: Question): boolean {
    const kind = this.kind(q);
    if (kind === 'FIB') {
      return this.getFibMark(q.number) === true;
    }
    if (q.answer === undefined || q.answer === null) return false;
    const answer = this.getAnswer(q.number);

    if (kind === 'MATRIX' || kind === 'BOWTIE') {
      const expected = q.answer && typeof q.answer === 'object' && !Array.isArray(q.answer)
        ? (q.answer as Record<string, string[]>)
        : {};
      const user = answer && typeof answer === 'object' && !Array.isArray(answer)
        ? (answer as Record<string, string[]>)
        : {};
      return this.groupedEqual(expected, user);
    }
    if (kind === 'CLOZE') {
      const expected = Array.isArray(q.answer) ? (q.answer as string[]) : [];
      const user = Array.isArray(answer) ? (answer as string[]) : [];
      return (
        expected.length === user.length &&
        expected.every((e, i) => String(user[i] ?? '').trim().toLowerCase() === String(e).trim().toLowerCase())
      );
    }
    if (kind === 'RANKING') {
      const expected = Array.isArray(q.answer) ? (q.answer as string[]).map(String) : [];
      const user = Array.isArray(answer) ? (answer as string[]).map(String) : [];
      return expected.length === user.length && expected.every((e, i) => e.trim() === user[i].trim());
    }
    if (kind === 'HIGHLIGHT') {
      const expected = new Set(Array.isArray(q.answer) ? (q.answer as number[]).map(Number) : []);
      const user = new Set(Array.isArray(answer) ? (answer as number[]).map(Number) : []);
      return expected.size === user.size && [...expected].every((e) => user.has(e));
    }
    if (kind === 'HOTSPOT') {
      return String(answer ?? '') === String(q.answer);
    }
    if (kind === 'SATA') {
      const expectedArr = Array.isArray(q.answer)
        ? (q.answer as string[]).map(String)
        : String(q.answer).split(',').map((s) => s.trim());
      const expected = new Set(expectedArr);
      const userArr = Array.isArray(answer) ? (answer as string[]).map(String) : [];
      const userSet = new Set(userArr);
      return expected.size === userSet.size && [...expected].every((e) => userSet.has(e));
    }
    return answer === (Array.isArray(q.answer) ? String(q.answer[0]) : q.answer);
  }

  private groupedEqual(a: Record<string, string[]>, b: Record<string, string[]>): boolean {
    const norm = (m: Record<string, string[]>) => {
      const out: Record<string, Set<string>> = {};
      for (const [k, v] of Object.entries(m)) {
        const s = new Set((v ?? []).map((x) => String(x).trim()).filter(Boolean));
        if (s.size) out[String(k).trim()] = s;
      }
      return out;
    };
    const na = norm(a);
    const nb = norm(b);
    const keysA = Object.keys(na);
    if (keysA.length !== Object.keys(nb).length) return false;
    return keysA.every((k) => {
      const sa = na[k];
      const sb = nb[k];
      return !!sb && sa.size === sb.size && [...sa].every((x) => sb.has(x));
    });
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
    this.scheduleAutoSave();
  }

  isFlagged(qNum: number): boolean {
    return this.flagged().has(qNum);
  }

  isAnswered(qNum: number): boolean {
    const ans = this.answers().get(qNum);
    if (ans === undefined || ans === null) return false;
    if (Array.isArray(ans)) return ans.length > 0;
    if (typeof ans === 'object') {
      return Object.values(ans).some((v) => Array.isArray(v) && v.length > 0);
    }
    return ans !== '';
  }

  /** True when every part of a multi-part question has a selection (used to enable Check Answer). */
  isFullyAnswered(q: Question): boolean {
    const kind = this.kind(q);
    if (kind === 'MATRIX') {
      const ans = this.matrixAnswer(q.number);
      return this.matrixRows(q).every((_, i) => (ans[String(i)] ?? []).length > 0);
    }
    if (kind === 'CLOZE') {
      const blanks = this.clozeBlanks(q);
      return blanks.length > 0 && blanks.every((_, i) => this.getClozeAnswer(q.number, i) !== '');
    }
    if (kind === 'BOWTIE') {
      const ans = this.bowtieAnswer(q.number);
      return this.bowtieCategories(q).every((c) => (ans[c.name] ?? []).length >= (c.count || 1));
    }
    return this.isAnswered(q.number);
  }

  // ── Auto-save ──────────────────────────────────────────────

  private scheduleAutoSave(): void {
    if (this.autoSaveTimeout) clearTimeout(this.autoSaveTimeout);
    this.autoSaveTimeout = setTimeout(() => this.persistProgress(), 500);
  }

  private persistProgress(): void {
    if (this.questions().length === 0) return;
    this.autoSaveStatus.set('saving');

    const answersObj: Record<string, AnswerValue> = {};
    for (const [key, val] of this.answers()) {
      answersObj[String(key)] = val;
    }

    this.examService
      .saveProgress({
        exam_id: this.examId,
        mode: this.mode(),
        answers: answersObj,
        flagged: [...this.flagged()],
        question_order: this.questions().map((q) => q.number),
        remaining_seconds: this.remainingSeconds(),
        current_page: this.currentPage(),
      })
      .subscribe({
        next: () => {
          this.autoSaveStatus.set('saved');
          setTimeout(() => {
            if (this.autoSaveStatus() === 'saved') this.autoSaveStatus.set('idle');
          }, 2000);
        },
        error: () => this.autoSaveStatus.set('idle'),
      });
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
    const timeSpent = this.timeLimitSeconds() - this.remainingSeconds();
    const subs: AnswerSubmission[] = this.questions().map((q) => ({
      question_number: q.number,
      answer: this.answers().get(q.number) ?? (q.type === 'SATA' ? [] : ''),
      fib_correct: this.getFibMark(q.number) ?? null,
    }));

    this.examService
      .submitExam({
        exam_id: this.examId,
        answers: subs,
        time_spent_seconds: timeSpent,
        mode: this.mode(),
        question_numbers: this.questions().map((q) => q.number),
      })
      .subscribe({
        next: (result) => {
          this.submitting.set(false);
          this.examService
            .deleteInProgressByExam(this.examId, this.mode())
            .subscribe({ error: () => {} });
          this.router.navigate(['/results', result.id]);
        },
        error: () => {
          this.submitting.set(false);
          alert('Submission failed. Please try again.');
        },
      });
  }
}
