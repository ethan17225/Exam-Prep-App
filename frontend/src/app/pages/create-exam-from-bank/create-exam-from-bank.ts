import { Component, OnInit, computed, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Course, ExamService, QuestionBankDetail } from '../../services/exam.service';
import { allocateSectionDraws } from '../../components/question-editor/question-draft';

const DEFAULT_PASS_GRADE = 72;

@Component({
  selector: 'app-create-exam-from-bank',
  imports: [FormsModule],
  templateUrl: './create-exam-from-bank.html',
  styleUrl: './create-exam-from-bank.scss',
})
export class CreateExamFromBankPage implements OnInit {
  bank = signal<QuestionBankDetail | null>(null);
  loading = signal(true);
  loadError = signal('');
  error = signal('');
  submitting = signal(false);

  title = signal('');
  courses = signal<Course[]>([]);
  selectedCourseId = signal('');
  timeLimitMinutes = signal<number | null>(null);
  passGrade = signal<number | null>(DEFAULT_PASS_GRADE);
  shuffle = signal(true);
  percents = signal<Record<string, number>>({});
  questionsPerAttempt = signal<number | null>(null);

  poolSize = computed(() => {
    const bank = this.bank();
    if (!bank) return 0;
    const percents = this.percents();
    return bank.sections.reduce((sum, s) => {
      const percent = Number(percents[s.id] ?? 0);
      return sum + (percent >= 1 ? s.question_count : 0);
    }, 0);
  });

  preview = computed(() => {
    const bank = this.bank();
    if (!bank) return [];
    const percents = this.percents();
    const sizes = bank.sections.map((s) =>
      Number(percents[s.id] ?? 0) >= 1 ? s.question_count : 0,
    );
    const weights = bank.sections.map((s) => Number(percents[s.id] ?? 0));
    const total = this.questionsPerAttempt();
    const draws = allocateSectionDraws(total, sizes, weights);
    return bank.sections.map((s, i) => ({
      id: s.id,
      name: s.name,
      size: s.question_count,
      percent: weights[i] ?? 0,
      n: draws[i] ?? 0,
    }));
  });

  totalDraw = computed(() => this.preview().reduce((sum, row) => sum + row.n, 0));

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    const bankId = this.route.snapshot.paramMap.get('id')!;
    this.examService.listCourses().subscribe({
      next: (data) => this.courses.set(data),
      error: () => {},
    });
    this.examService.getBank(bankId).subscribe({
      next: (bank) => {
        this.bank.set(bank);
        this.title.set(bank.title);
        if (bank.course_id) this.selectedCourseId.set(bank.course_id);
        const withQuestions = bank.sections.filter((s) => s.question_count > 0);
        const base = withQuestions.length ? Math.floor(100 / withQuestions.length) : 0;
        const extra = withQuestions.length ? 100 - base * withQuestions.length : 0;
        const percents: Record<string, number> = {};
        let filled = 0;
        for (const s of bank.sections) {
          if (!s.question_count) {
            percents[s.id] = 0;
            continue;
          }
          percents[s.id] = base + (filled < extra ? 1 : 0);
          filled += 1;
        }
        this.percents.set(percents);
        const pool = bank.sections.reduce((sum, s) => sum + s.question_count, 0);
        this.questionsPerAttempt.set(pool || null);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Could not load this bank.');
      },
    });
  }

  setPercent(sectionId: string, value: number): void {
    this.percents.set({ ...this.percents(), [sectionId]: value });
  }

  goBack(): void {
    const bank = this.bank();
    if (bank) this.router.navigate(['/banks', bank.id]);
    else this.router.navigate(['/banks']);
  }

  submit(): void {
    const bank = this.bank();
    if (!bank) return;
    this.error.set('');
    const titleVal = this.title().trim();
    if (!titleVal) {
      this.error.set('Please enter an exam title.');
      return;
    }
    const grade = this.passGrade();
    if (grade == null || !Number.isFinite(grade) || grade < 1 || grade > 100) {
      this.error.set('Pass grade is required and must be between 1 and 100.');
      return;
    }
    const shares = this.preview()
      .filter((row) => row.percent >= 1)
      .map((row) => ({ section_id: row.id, percent: Math.round(row.percent) }));
    if (!shares.length) {
      this.error.set('Set section percentages so the exam draws at least one question.');
      return;
    }
    let attemptSize = this.questionsPerAttempt();
    const pool = this.poolSize();
    if (attemptSize == null || !Number.isFinite(attemptSize) || attemptSize < 1) {
      this.error.set('Choose how many questions students sit per attempt.');
      return;
    }
    attemptSize = Math.floor(attemptSize);
    if (attemptSize > pool) {
      this.error.set(`Cannot exceed the ${pool} questions in the selected sections.`);
      return;
    }
    if (this.totalDraw() < 1) {
      this.error.set('Set section percentages so the exam draws at least one question.');
      return;
    }
    let timeLimit = this.timeLimitMinutes();
    if (timeLimit && timeLimit <= 0) timeLimit = null;

    this.submitting.set(true);
    this.examService
      .createExamFromBank({
        title: titleVal,
        bank_id: bank.id,
        shares,
        questions_per_attempt: attemptSize,
        course_id: this.selectedCourseId() || undefined,
        time_limit_minutes: timeLimit,
        pass_grade: Math.round(grade),
        shuffle: this.shuffle(),
      })
      .subscribe({
        next: () => this.router.navigate(['/exams']),
        error: (err) => {
          this.submitting.set(false);
          this.error.set(err?.error?.detail || 'Failed to create exam.');
        },
      });
  }
}
