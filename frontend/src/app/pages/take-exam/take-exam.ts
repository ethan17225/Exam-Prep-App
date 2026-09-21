import {
  Component,
  OnInit,
  OnDestroy,
  signal,
  computed,
  Injector,
  afterNextRender,
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { map, of, switchMap } from 'rxjs';
import { QuestionSectionsComponent } from '../../components/question-sections/question-sections';
import { AuthService, PROGRESS_KEY_PREFIX } from '../../services/auth.service';
import {
  ExamService,
  Question,
  AnswerSubmission,
  AnswerValue,
  InProgressExam,
  SaveProgressPayload,
  QuestionKind,
  BowtieCategory,
  ClozeBlank,
  HotspotRegion,
  questionKindCounts,
  classifyQuestionType,
  formatAnswerForDisplay,
  formatClock,
  isAnswerCorrect,
  shuffle,
  shuffleQuestionOptions,
  applyOptionOrder,
  matrixRows,
  matrixColumns,
  clozeBlanks,
  bowtieCategories,
  highlightTokens,
  hotspotRegions,
  rankingItems,
} from '../../services/exam.service';

/** Static per-question structure, parsed once per page instead of on every change-detection pass. */
interface QuestionStructVm {
  kind: QuestionKind;
  advanced: boolean;
  options: string[];
  matrixRows: string[];
  matrixCols: string[];
  cloze: ClozeBlank[];
  bowtie: BowtieCategory[];
  tokens: string[];
  regions: HotspotRegion[];
}

/** Answer-dependent per-question state; recomputes on interaction, never on the 1 Hz timer tick. */
interface QuestionStateVm {
  correct: boolean;
  fullyAnswered: boolean;
  rankOrder: string[];
  hotspotLabel: string;
  correctText: string;
}

/** One count chip in the sticky header's type strip. */
interface TypeChipVm {
  kind: QuestionKind;
  count: number;
  tone: 'mcq' | 'sata' | 'fib' | 'other';
}

/** The six advanced kinds share the one amber chip colour; the three common kinds have their own. */
function chipTone(kind: QuestionKind): TypeChipVm['tone'] {
  if (kind === 'MCQ') return 'mcq';
  if (kind === 'SATA') return 'sata';
  if (kind === 'FIB') return 'fib';
  return 'other';
}

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
  loading = signal(true);
  loadError = signal('');
  autoSaveStatus = signal<'idle' | 'saving' | 'saved' | 'error'>('idle');

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
  private shuffleEnabled = false;

  totalQuestions = computed(() => this.questions().length);
  typeChips = computed<TypeChipVm[]>(() =>
    questionKindCounts(this.questions()).map(({ kind, count }) => ({
      kind,
      count,
      tone: chipTone(kind),
    })),
  );
  answeredCount = computed(() => this.answers().size);
  progress = computed(() =>
    this.totalQuestions() > 0
      ? Math.round((this.answeredCount() / this.totalQuestions()) * 100)
      : 0,
  );

  totalPages = computed(() => Math.ceil(this.totalQuestions() / this.questionsPerPage));
  pageQuestions = computed(() => {
    const start = this.currentPage() * this.questionsPerPage;
    return this.questions().slice(start, start + this.questionsPerPage);
  });
  pageStartNum = computed(() => this.currentPage() * this.questionsPerPage + 1);
  pageEndNum = computed(() =>
    Math.min((this.currentPage() + 1) * this.questionsPerPage, this.totalQuestions()),
  );

  structVm = computed<Map<number, QuestionStructVm>>(() => {
    const vms = new Map<number, QuestionStructVm>();
    for (const q of this.pageQuestions()) {
      const kind = classifyQuestionType(q);
      vms.set(q.id, {
        kind,
        advanced: kind !== 'MCQ' && kind !== 'SATA' && kind !== 'FIB',
        options: Array.isArray(q.options) ? q.options : [],
        matrixRows: kind === 'MATRIX' ? matrixRows(q) : [],
        matrixCols: kind === 'MATRIX' ? matrixColumns(q) : [],
        cloze: kind === 'CLOZE' ? clozeBlanks(q) : [],
        bowtie: kind === 'BOWTIE' ? bowtieCategories(q) : [],
        tokens: kind === 'HIGHLIGHT' ? highlightTokens(q) : [],
        regions: kind === 'HOTSPOT' ? hotspotRegions(q) : [],
      });
    }
    return vms;
  });

  stateVm = computed<Map<number, QuestionStateVm>>(() => {
    const struct = this.structVm();
    const vms = new Map<number, QuestionStateVm>();
    for (const q of this.pageQuestions()) {
      const s = struct.get(q.id)!;
      const revealed = this.revealed().has(q.id);
      vms.set(q.id, {
        correct: revealed && this.isQuestionCorrect(q),
        fullyAnswered: this.isFullyAnswered(q),
        rankOrder: s.kind === 'RANKING' ? this.rankOrder(q) : [],
        hotspotLabel: s.kind === 'HOTSPOT' ? this.hotspotSelectedLabel(q) : '',
        correctText: revealed && s.advanced ? formatAnswerForDisplay(q, q.answer ?? null) : '',
      });
    }
    return vms;
  });

  navVm = computed(() => {
    const answers = this.answers();
    const flagged = this.flagged();
    const page = this.currentPage();
    return this.questions().map((q, i) => ({
      id: q.id,
      index: i,
      answered: this.isAnsweredValue(answers.get(q.id)),
      flagged: flagged.has(q.id),
      current: Math.floor(i / this.questionsPerPage) === page,
    }));
  });

  formattedTime = computed(() => formatClock(this.remainingSeconds()));

  timerWarning = computed(() => this.remainingSeconds() <= 300 && this.remainingSeconds() > 60);
  timerDanger = computed(() => this.remainingSeconds() <= 60);

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
    private auth: AuthService,
    private injector: Injector,
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

    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');

    const practice = this.mode() === 'practice';

    this.examService
      // Answers are requested ONLY for practice. A graded run must never have the
      // key in the browser — it is one devtools panel away from the student.
      .getExam(this.examId, practice, this.mode())
      .pipe(
        switchMap((exam) =>
          this.resumeId
            ? this.examService
                .getInProgress(this.resumeId)
                .pipe(map((saved) => ({ exam, saved: saved as InProgressExam | null })))
            : of({ exam, saved: null as InProgressExam | null }),
        ),
      )
      .subscribe({
        next: ({ exam, saved }) => {
          if (practice && !exam.allow_practice) {
            this.loading.set(false);
            this.loadError.set('This exam is assessment-only, so practice mode is disabled.');
            return;
          }

          this.examTitle.set(exam.title);
          this.shuffleEnabled = !!exam.shuffle;

          const limit = exam.time_limit_minutes ? exam.time_limit_minutes * 60 : 180 * 60;
          this.timeLimitSeconds.set(limit);

          if (saved) {
            this.restoreProgress(exam.questions, saved);
            this.loading.set(false);
            this.startTimer();
          } else if (exam.bank_backed) {
            this.questions.set([]);
            this.remainingSeconds.set(limit);
            this.persistProgress({
              allowEmpty: true,
              onError: (err) =>
                this.loadError.set(
                  err?.error?.detail ||
                    'Could not start this attempt. Check your connection and try again — ' +
                      'do not begin answering until it starts.',
                ),
              onSuccess: () => {
                this.examService.getExam(this.examId, practice, this.mode()).subscribe({
                  next: (drawn) => {
                    this.questions.set(this.withShuffledOptions(drawn.questions));
                    this.persistProgress();
                    this.loading.set(false);
                    this.startTimer();
                  },
                  error: (err) => {
                    this.loading.set(false);
                    this.loadError.set(
                      err?.error?.detail ||
                        'The attempt started but the questions could not be loaded.',
                    );
                  },
                });
              },
            });
          } else {
            // Prefer the exam's own attempt size over a leftover ?count= query
            // param from older bookmarks; the query param is still accepted as a
            // practice override when the exam itself has no limit.
            const pool = exam.shuffle ? shuffle([...exam.questions]) : [...exam.questions];
            const configured =
              exam.questions_per_attempt != null
                ? exam.questions_per_attempt
                : this.selectedQuestionCount;
            const takeCount = configured
              ? Math.min(Math.max(configured, 1), pool.length)
              : pool.length;
            this.questions.set(this.withShuffledOptions(pool.slice(0, takeCount)));
            this.remainingSeconds.set(limit);
            // The first save is what creates the attempt server-side. If it
            // fails there is nothing to submit into later, so block rather than
            // let someone sit a whole paper they cannot hand in.
            this.persistProgress({
              onError: () =>
                this.loadError.set(
                  'Could not start this attempt. Check your connection and try again — ' +
                    'do not begin answering until it starts.',
                ),
              onSuccess: () => {
                this.loading.set(false);
                this.startTimer();
              },
            });
          }
        },
        error: (err) => {
          this.loading.set(false);
          this.loadError.set(
            err?.error?.detail || 'Failed to load the exam. Check your connection and try again.',
          );
        },
      });
  }

  private startTimer(): void {
    if (this.timerInterval) clearInterval(this.timerInterval);
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
    // If the last autosave never reached the server, the local mirror is newer.
    const local = this.readLocalProgress(saved.saved_at);
    const source = local ?? saved;

    const questionMap = new Map(allQuestions.map((q) => [q.id, q]));
    const ordered = source.question_order
      .map((qid) => questionMap.get(qid))
      .filter((q): q is Question => !!q);
    const paper = ordered.length ? ordered : [...allQuestions];
    const frozen = source.option_order;
    const hasFrozen = !!frozen && Object.keys(frozen).length > 0;
    this.questions.set(
      hasFrozen ? applyOptionOrder(paper, frozen) : this.withShuffledOptions(paper),
    );

    const restoredAnswers = new Map<number, AnswerValue>();
    for (const [key, val] of Object.entries(source.answers)) {
      restoredAnswers.set(Number(key), val);
    }
    this.answers.set(restoredAnswers);
    this.flagged.set(new Set(source.flagged));
    this.remainingSeconds.set(source.remaining_seconds);
    this.currentPage.set(source.current_page);
  }

  private withShuffledOptions(questions: Question[]): Question[] {
    if (!this.shuffleEnabled) return questions;
    return questions.map(shuffleQuestionOptions);
  }

  ngOnDestroy(): void {
    if (this.timerInterval) clearInterval(this.timerInterval);
    if (this.autoSaveTimeout) clearTimeout(this.autoSaveTimeout);
  }

  // ── Page Navigation ─────────────────────────────────────────

  goTo(index: number): void {
    const page = Math.floor(index / this.questionsPerPage);
    const pageChanged = page !== this.currentPage();
    const qid = this.questions()[index]?.id;
    this.currentPage.set(page);
    this.showNav.set(false);
    if (qid == null) return;

    const scrollToQuestion = (): void => {
      const el = document.getElementById(`q-${qid}`);
      if (!el) return;
      const header = document.querySelector('.exam-header-sticky') as HTMLElement | null;
      const offset = (header?.offsetHeight ?? 0) + 12;
      const top = el.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    };

    if (pageChanged) {
      // Wait until the new page's cards are painted before scrolling to one.
      afterNextRender(scrollToQuestion, { injector: this.injector });
    } else {
      scrollToQuestion();
    }
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

  // ── Answering ───────────────────────────────────────────────

  private kind(q: Question): QuestionKind {
    return classifyQuestionType(q);
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

  private matrixAnswer(qNum: number): Record<string, string[]> {
    const ans = this.answers().get(qNum);
    return ans && typeof ans === 'object' && !Array.isArray(ans)
      ? (ans as Record<string, string[]>)
      : {};
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

  private clozeAnswer(qNum: number, blankCount: number): string[] {
    const ans = this.answers().get(qNum);
    const list = Array.isArray(ans) ? [...(ans as string[])] : [];
    while (list.length < blankCount) list.push('');
    return list;
  }

  setClozeAnswer(q: Question, blankIdx: number, value: string): void {
    if (this.isRevealed(q.id)) return;
    const list = this.clozeAnswer(q.id, clozeBlanks(q).length);
    list[blankIdx] = value;
    this.setAnswer(q.id, list);
  }

  getClozeAnswer(qNum: number, blankIdx: number): string {
    const ans = this.answers().get(qNum);
    return Array.isArray(ans) ? String((ans as string[])[blankIdx] ?? '') : '';
  }

  clozeExpected(q: Question, blankIdx: number): string {
    return Array.isArray(q.answer) ? String((q.answer as string[])[blankIdx] ?? '') : '';
  }

  isClozeBlankCorrect(q: Question, blankIdx: number): boolean {
    const user = this.getClozeAnswer(q.id, blankIdx).trim().toLowerCase();
    return !!user && user === this.clozeExpected(q, blankIdx).trim().toLowerCase();
  }

  // ── BOWTIE ──────────────────────────────────────────────────

  private bowtieAnswer(qNum: number): Record<string, string[]> {
    const ans = this.answers().get(qNum);
    return ans && typeof ans === 'object' && !Array.isArray(ans)
      ? (ans as Record<string, string[]>)
      : {};
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

  private rankOrder(q: Question): string[] {
    const ans = this.answers().get(q.id);
    if (Array.isArray(ans) && ans.length > 0) return ans as string[];
    return rankingItems(q);
  }

  moveRank(q: Question, index: number, delta: number): void {
    if (this.isRevealed(q.id)) return;
    const order = [...this.rankOrder(q)];
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    this.setAnswer(q.id, order);
  }

  confirmRankOrder(q: Question): void {
    if (this.isRevealed(q.id)) return;
    this.setAnswer(q.id, [...this.rankOrder(q)]);
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

  private hotspotSelectedLabel(q: Question): string {
    const ans = this.answers().get(q.id);
    if (!ans || typeof ans !== 'string') return '';
    return hotspotRegions(q).find((r) => r.id === ans)?.label ?? '';
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
    const letters = String(q.answer ?? '')
      .split(',')
      .map((s) => s.trim());
    return letters.includes(letter);
  }

  private isQuestionCorrect(q: Question): boolean {
    // FIB is self-marked in practice mode; everything else grades exactly as the server does.
    if (this.kind(q) === 'FIB') return this.getFibMark(q.id) === true;
    return isAnswerCorrect(q, this.getAnswer(q.id) ?? null);
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

  private isAnsweredValue(ans: AnswerValue | undefined): boolean {
    if (ans === undefined || ans === null) return false;
    if (Array.isArray(ans)) return ans.length > 0;
    if (typeof ans === 'object') {
      return Object.values(ans).some((v) => Array.isArray(v) && v.length > 0);
    }
    return ans !== '';
  }

  isAnswered(qNum: number): boolean {
    return this.isAnsweredValue(this.answers().get(qNum));
  }

  /** True when every part of a multi-part question has a selection (used to enable Check Answer). */
  private isFullyAnswered(q: Question): boolean {
    const kind = this.kind(q);
    if (kind === 'MATRIX') {
      const ans = this.matrixAnswer(q.id);
      return matrixRows(q).every((_, i) => (ans[String(i)] ?? []).length > 0);
    }
    if (kind === 'CLOZE') {
      const blanks = clozeBlanks(q);
      return blanks.length > 0 && blanks.every((_, i) => this.getClozeAnswer(q.id, i) !== '');
    }
    if (kind === 'BOWTIE') {
      const ans = this.bowtieAnswer(q.id);
      return bowtieCategories(q).every((c) => (ans[c.name] ?? []).length >= (c.count || 1));
    }
    return this.isAnswered(q.id);
  }

  // ── Auto-save ──────────────────────────────────────────────

  private scheduleAutoSave(): void {
    if (this.autoSaveTimeout) clearTimeout(this.autoSaveTimeout);
    this.autoSaveTimeout = setTimeout(() => this.persistProgress(), 500);
  }

  /** Key for the local mirror of this attempt. */
  private localKey(): string {
    // Scoped by user: without it, two students sharing a browser resume each
    // other's answers, because restoreProgress prefers the newer mirror.
    return `${PROGRESS_KEY_PREFIX}${this.auth.user()?.id ?? 'anon'}_${this.examId}_${this.mode()}`;
  }

  private persistProgress(hooks?: {
    onSuccess?: () => void;
    onError?: (err?: { error?: { detail?: string } }) => void;
    allowEmpty?: boolean;
  }): void {
    if (this.questions().length === 0 && !hooks?.allowEmpty) return;
    this.autoSaveStatus.set('saving');

    const answersObj: Record<string, AnswerValue> = {};
    for (const [key, val] of this.answers()) {
      answersObj[String(key)] = val;
    }
    const optionOrder: Record<string, NonNullable<Question['options']>> = {};
    for (const q of this.questions()) {
      if (q.options != null) optionOrder[String(q.id)] = q.options;
    }

    const payload = {
      exam_id: this.examId,
      mode: this.mode(),
      answers: answersObj,
      flagged: [...this.flagged()],
      question_order: this.questions().map((q) => q.id),
      option_order: optionOrder,
      remaining_seconds: this.remainingSeconds(),
      current_page: this.currentPage(),
    };

    // Mirror locally before the request. An expired token, a network blip, or a
    // backend restart mid-exam must never cost the student their answers.
    try {
      localStorage.setItem(this.localKey(), JSON.stringify({ savedAt: Date.now(), payload }));
    } catch {
      // Quota or private-mode failure — the server save below is still attempted.
    }

    this.examService.saveProgress(payload).subscribe({
      next: (saved) => {
        this.autoSaveStatus.set('saved');
        // Re-sync the countdown from the server's started_at. The local mirror
        // is student-writable, so it must not be what decides how much time is
        // left on a graded attempt.
        if (this.mode() === 'exam' && saved?.started_at) {
          const elapsed = (Date.now() - new Date(saved.started_at).getTime()) / 1000;
          this.remainingSeconds.set(Math.max(0, Math.round(this.timeLimitSeconds() - elapsed)));
        }
        setTimeout(() => {
          if (this.autoSaveStatus() === 'saved') this.autoSaveStatus.set('idle');
        }, 2000);
        hooks?.onSuccess?.();
      },
      // 'idle' looked identical to "nothing to save", so a whole exam could fail
      // to save with no visible hint. Surface it.
      error: (err) => {
        this.autoSaveStatus.set('error');
        hooks?.onError?.(err);
      },
    });
  }

  /** Local mirror for this attempt, if it is newer than what the server returned. */
  private readLocalProgress(serverSavedAt: string | null): SaveProgressPayload | null {
    try {
      const raw = localStorage.getItem(this.localKey());
      if (!raw) return null;
      const { savedAt, payload } = JSON.parse(raw) as {
        savedAt: number;
        payload: SaveProgressPayload;
      };
      if (serverSavedAt && new Date(serverSavedAt).getTime() >= savedAt) return null;
      return payload;
    } catch {
      return null;
    }
  }

  private clearLocalProgress(): void {
    try {
      localStorage.removeItem(this.localKey());
    } catch {
      // Nothing to do — a stale mirror is discarded on the next successful save.
    }
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
    const practice = this.mode() === 'practice';
    const timeSpent = this.timeLimitSeconds() - this.remainingSeconds();
    const subs: AnswerSubmission[] = this.questions().map((q) => ({
      question_id: q.id,
      answer: this.answers().get(q.id) ?? (this.kind(q) === 'SATA' ? [] : ''),
      // Self-marking is a study aid. The server ignores it for a graded run, so
      // do not imply a contract that no longer exists.
      fib_correct: practice ? (this.getFibMark(q.id) ?? null) : null,
    }));

    this.examService
      .submitExam({
        exam_id: this.examId,
        answers: subs,
        // Ignored for graded runs — the server times the attempt from its own
        // started_at — but practice attempts still report their own duration.
        time_spent_seconds: timeSpent,
        mode: this.mode(),
        // Likewise ignored when graded: the whole paper is scored.
        ...(practice ? { question_ids: this.questions().map((q) => q.id) } : {}),
      })
      .subscribe({
        next: (result) => {
          this.submitting.set(false);
          this.clearLocalProgress();
          // The server consumes the attempt inside the submit transaction, so
          // there is nothing left to discard here.
          this.router.navigate(['/results', result.id]);
        },
        error: (err) => {
          this.submitting.set(false);
          if (err?.status === 409) {
            // Already submitted, or the attempt was reset. Nothing to retry.
            this.clearLocalProgress();
            alert(err?.error?.detail || 'This attempt is no longer open.');
            this.router.navigate(['/history']);
            return;
          }
          // Otherwise the local mirror is deliberately left in place: reopening
          // the exam restores these answers rather than losing them.
          alert(
            err?.error?.detail ||
              'Submission failed. Your answers are saved on this device — sign in again and reopen the exam to retry.',
          );
        },
      });
  }
}
