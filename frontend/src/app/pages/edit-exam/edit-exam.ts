import { Component, OnDestroy, OnInit, computed, signal, WritableSignal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService, SectionShare } from '../../services/exam.service';
import { QuestionEditorCardComponent } from '../../components/question-editor/question-editor-card';
import {
  DEFAULT_MCQ_PAYLOAD,
  QuestionDraft,
  allocateSectionDraws,
  serialize,
  serializeSections,
  toDraft,
} from '../../components/question-editor/question-draft';

@Component({
  selector: 'app-edit-exam',
  imports: [FormsModule, QuestionEditorCardComponent],
  templateUrl: './edit-exam.html',
  styleUrl: './edit-exam.scss',
})
export class EditExamPage implements OnInit, OnDestroy {
  examTitle = signal('');
  drafts = signal<QuestionDraft[]>([]);
  loading = signal(true);
  loadError = signal('');
  addingQuestion = signal(false);

  timeLimitMinutes = signal<number | null>(null);
  questionsPerAttempt = signal<number | null>(null);
  shuffle = signal(true);
  totalQuestions = signal(0);
  savingSettings = signal(false);
  settingsError = signal('');
  settingsSaved = signal(false);

  bankId = signal<string | null>(null);
  sectionShares = signal<SectionShare[]>([]);

  sharePreview = computed(() => {
    const shares = this.sectionShares();
    const draws = allocateSectionDraws(
      this.questionsPerAttempt(),
      shares.map((s) => s.question_count),
      shares.map((s) => Number(s.percent)),
    );
    return shares.map((s, i) => ({ ...s, n: draws[i] ?? 0 }));
  });

  expanded = signal<Record<number, boolean>>({});
  saving = signal<Record<number, boolean>>({});
  saved = signal<Record<number, boolean>>({});
  uploading = signal<Record<number, boolean>>({});
  draftError = signal<Record<number, string>>({});

  private examId = '';
  private savedTimers = new Map<number, ReturnType<typeof setTimeout>>();
  private settingsSavedTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    this.examId = this.route.snapshot.paramMap.get('id')!;
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.getExam(this.examId, true).subscribe({
      next: (exam) => {
        if (!exam.is_owner) {
          this.loading.set(false);
          this.loadError.set('You can only edit exams you created.');
          return;
        }
        this.examTitle.set(exam.title);
        this.timeLimitMinutes.set(exam.time_limit_minutes ?? null);
        this.questionsPerAttempt.set(exam.questions_per_attempt ?? null);
        this.shuffle.set(exam.shuffle ?? true);
        this.bankId.set(exam.bank_id ?? null);
        this.sectionShares.set(exam.section_shares ?? []);
        if (exam.bank_backed) {
          const shares = exam.section_shares ?? [];
          const pool = shares.reduce((sum, s) => sum + s.question_count, 0);
          this.totalQuestions.set(pool);
          const draws = allocateSectionDraws(
            exam.questions_per_attempt,
            shares.map((s) => s.question_count),
            shares.map((s) => s.percent),
          );
          const expected = draws.reduce((sum, n) => sum + n, 0);
          this.questionsPerAttempt.set((exam.questions_per_attempt ?? expected) || pool || null);
          this.drafts.set([]);
        } else {
          this.totalQuestions.set(exam.questions.length);
          this.drafts.set(exam.questions.map((q) => toDraft(q)));
        }
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Could not load this exam.');
      },
    });
  }

  ngOnDestroy(): void {
    for (const t of this.savedTimers.values()) clearTimeout(t);
    this.savedTimers.clear();
    if (this.settingsSavedTimer) clearTimeout(this.settingsSavedTimer);
  }

  goBack(): void {
    this.router.navigate(['/exams']);
  }

  goToBank(): void {
    const id = this.bankId();
    if (id) this.router.navigate(['/banks', id]);
  }

  setSharePercent(sectionId: string, percent: number): void {
    this.sectionShares.set(
      this.sectionShares().map((s) => (s.section_id === sectionId ? { ...s, percent } : s)),
    );
  }

  saveSettings(): void {
    this.settingsError.set('');
    const bankBacked = !!this.bankId();
    let attemptSize = this.questionsPerAttempt();
    if (attemptSize != null) {
      if (!Number.isFinite(attemptSize) || attemptSize < 1) {
        this.settingsError.set(
          'Questions per attempt must be a positive number, or blank for all.',
        );
        return;
      }
      attemptSize = Math.floor(attemptSize);
      if (this.totalQuestions() > 0 && attemptSize > this.totalQuestions()) {
        this.settingsError.set(`Cannot exceed the exam's ${this.totalQuestions()} questions.`);
        return;
      }
    } else if (bankBacked) {
      this.settingsError.set('Choose how many questions students sit per attempt.');
      return;
    }

    let timeLimit = this.timeLimitMinutes();
    if (timeLimit != null && timeLimit <= 0) timeLimit = null;

    const shares = bankBacked
      ? this.sectionShares().map((s) => ({ section_id: s.section_id, percent: Number(s.percent) }))
      : undefined;
    if (shares) {
      for (const s of shares) {
        if (!Number.isFinite(s.percent) || s.percent < 1 || s.percent > 100) {
          this.settingsError.set('Each section percent must be between 1 and 100.');
          return;
        }
      }
    }

    this.savingSettings.set(true);
    this.examService
      .updateExamSettings(this.examId, {
        timeLimitMinutes: timeLimit,
        shuffle: this.shuffle(),
        questionsPerAttempt: attemptSize,
        clearQuestionsPerAttempt: !bankBacked && attemptSize == null,
        shares,
      })
      .subscribe({
        next: (exam) => {
          this.savingSettings.set(false);
          this.timeLimitMinutes.set(exam.time_limit_minutes);
          this.questionsPerAttempt.set(exam.questions_per_attempt);
          this.shuffle.set(exam.shuffle);
          this.settingsSaved.set(true);
          if (this.settingsSavedTimer) clearTimeout(this.settingsSavedTimer);
          this.settingsSavedTimer = setTimeout(() => this.settingsSaved.set(false), 2000);
        },
        error: (err) => {
          this.savingSettings.set(false);
          this.settingsError.set(err?.error?.detail || 'Could not save settings.');
        },
      });
  }

  toggleExpand(d: QuestionDraft): void {
    this.expanded.set({ ...this.expanded(), [d.id]: !this.expanded()[d.id] });
  }

  replaceDraft(updated: QuestionDraft): void {
    this.drafts.update((list) => list.map((d) => (d.id === updated.id ? updated : d)));
  }

  private setFlag(sig: WritableSignal<Record<number, boolean>>, id: number, value: boolean): void {
    sig.set({ ...sig(), [id]: value });
  }

  private setError(id: number, message: string): void {
    this.draftError.set({ ...this.draftError(), [id]: message });
  }

  private currentDraft(id: number): QuestionDraft | undefined {
    return this.drafts().find((d) => d.id === id);
  }

  uploadImage(questionId: number, file: File): void {
    this.setFlag(this.uploading, questionId, true);
    this.setError(questionId, '');
    this.examService.uploadQuestionImage(questionId, file).subscribe({
      next: (res) => {
        const d = this.currentDraft(questionId);
        if (d) this.replaceDraft({ ...d, image: res.image });
        this.setFlag(this.uploading, questionId, false);
      },
      error: (err) => {
        this.setFlag(this.uploading, questionId, false);
        this.setError(questionId, err?.error?.detail || 'Image upload failed.');
      },
    });
  }

  removeImage(d: QuestionDraft): void {
    this.examService.deleteQuestionImage(d.id).subscribe({
      next: () => {
        const current = this.currentDraft(d.id) ?? d;
        this.replaceDraft({ ...current, image: null });
      },
      error: () => this.setError(d.id, 'Could not remove the image.'),
    });
  }

  save(clicked: QuestionDraft): void {
    const d = this.currentDraft(clicked.id) ?? clicked;
    this.setError(d.id, '');
    if (!d.question.trim()) {
      this.setError(d.id, 'Question text cannot be empty.');
      return;
    }
    const serialized = serialize(d);
    if ('error' in serialized) {
      this.setError(d.id, serialized.error);
      return;
    }
    this.setFlag(this.saving, d.id, true);
    this.examService
      .updateQuestion(this.examId, d.id, {
        topic: d.topic,
        type: d.type,
        question: d.question,
        sections: serializeSections(d),
        rationale: d.rationale,
        options: serialized.options as never,
        answer: serialized.answer as never,
      })
      .subscribe({
        next: () => {
          this.setFlag(this.saving, d.id, false);
          this.setFlag(this.saved, d.id, true);
          const existing = this.savedTimers.get(d.id);
          if (existing) clearTimeout(existing);
          this.savedTimers.set(
            d.id,
            setTimeout(() => this.setFlag(this.saved, d.id, false), 2000),
          );
        },
        error: (err) => {
          this.setFlag(this.saving, d.id, false);
          this.setError(d.id, err?.error?.detail || 'Save failed.');
        },
      });
  }

  deleteQuestion(d: QuestionDraft): void {
    if (!confirm('Delete this question? This cannot be undone.')) return;
    this.examService.deleteQuestion(this.examId, d.id).subscribe({
      next: () => {
        this.drafts.update((list) => list.filter((x) => x.id !== d.id));
        this.totalQuestions.set(Math.max(0, this.totalQuestions() - 1));
      },
      error: (err) => this.setError(d.id, err?.error?.detail || 'Delete failed.'),
    });
  }

  addQuestion(): void {
    this.addingQuestion.set(true);
    this.examService.addQuestion(this.examId, DEFAULT_MCQ_PAYLOAD).subscribe({
      next: (q) => {
        const draft = toDraft(q);
        this.drafts.update((list) => [...list, draft]);
        this.totalQuestions.set(this.totalQuestions() + 1);
        this.expanded.set({ ...this.expanded(), [draft.id]: true });
        this.addingQuestion.set(false);
      },
      error: (err) => {
        this.addingQuestion.set(false);
        alert(err?.error?.detail || 'Could not add a question.');
      },
    });
  }
}
