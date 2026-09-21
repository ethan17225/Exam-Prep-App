import { Component, OnDestroy, OnInit, signal, WritableSignal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService } from '../../services/exam.service';
import { QuestionEditorCardComponent } from '../../components/question-editor/question-editor-card';
import {
  DEFAULT_MCQ_PAYLOAD,
  QuestionDraft,
  serialize,
  serializeSections,
  toDraft,
} from '../../components/question-editor/question-draft';

interface EditorSection {
  id: string;
  name: string;
  position: number;
  drafts: QuestionDraft[];
  collapsed: boolean;
  pasteOpen: boolean;
  pasteText: string;
  pasteError: string;
  renaming: boolean;
  nameDraft: string;
}

@Component({
  selector: 'app-bank-editor',
  imports: [FormsModule, QuestionEditorCardComponent],
  templateUrl: './bank-editor.html',
  styleUrl: './bank-editor.scss',
})
export class BankEditorPage implements OnInit, OnDestroy {
  title = signal('');
  sections = signal<EditorSection[]>([]);
  loading = signal(true);
  loadError = signal('');
  newSectionName = signal('');
  addingSection = signal(false);
  addingQuestion = signal<Record<string, boolean>>({});
  expanded = signal<Record<number, boolean>>({});
  saving = signal<Record<number, boolean>>({});
  saved = signal<Record<number, boolean>>({});
  uploading = signal<Record<number, boolean>>({});
  draftError = signal<Record<number, string>>({});
  deleteError = signal('');

  private bankId = '';
  private savedTimers = new Map<number, ReturnType<typeof setTimeout>>();

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    this.bankId = this.route.snapshot.paramMap.get('id')!;
    this.load();
  }

  ngOnDestroy(): void {
    for (const t of this.savedTimers.values()) clearTimeout(t);
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.getBank(this.bankId).subscribe({
      next: (bank) => {
        this.title.set(bank.title);
        this.sections.set(
          bank.sections.map((s) => ({
            id: s.id,
            name: s.name,
            position: s.position,
            drafts: s.questions.map((q) => toDraft(q)),
            collapsed: false,
            pasteOpen: false,
            pasteText: '',
            pasteError: '',
            renaming: false,
            nameDraft: s.name,
          })),
        );
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Could not load this bank.');
      },
    });
  }

  goBack(): void {
    this.router.navigate(['/banks']);
  }

  createExam(): void {
    this.router.navigate(['/banks', this.bankId, 'create-exam']);
  }

  addSection(): void {
    const name = this.newSectionName().trim();
    if (!name) return;
    this.addingSection.set(true);
    this.examService.addBankSection(this.bankId, name).subscribe({
      next: (section) => {
        this.addingSection.set(false);
        this.newSectionName.set('');
        this.sections.update((list) => [
          ...list,
          {
            id: section.id,
            name: section.name,
            position: section.position,
            drafts: [],
            collapsed: false,
            pasteOpen: false,
            pasteText: '',
            pasteError: '',
            renaming: false,
            nameDraft: section.name,
          },
        ]);
      },
      error: (err) => {
        this.addingSection.set(false);
        this.loadError.set(err?.error?.detail || 'Could not add a section.');
      },
    });
  }

  saveSectionName(section: EditorSection): void {
    const name = section.nameDraft.trim();
    if (!name) return;
    this.examService.renameBankSection(this.bankId, section.id, name).subscribe({
      next: () => this.patchSection(section.id, { name, renaming: false, nameDraft: name }),
      error: (err) => {
        this.loadError.set(err?.error?.detail || 'Could not rename the section.');
      },
    });
  }

  deleteSection(section: EditorSection): void {
    if (!confirm(`Delete section “${section.name}” and its questions?`)) return;
    this.examService.deleteBankSection(this.bankId, section.id).subscribe({
      next: () => this.sections.update((list) => list.filter((s) => s.id !== section.id)),
      error: (err) => {
        this.deleteError.set(err?.error?.detail || 'Could not delete the section.');
      },
    });
  }

  toggleSection(section: EditorSection): void {
    this.patchSection(section.id, { collapsed: !section.collapsed });
  }

  togglePaste(section: EditorSection): void {
    this.patchSection(section.id, { pasteOpen: !section.pasteOpen, pasteError: '' });
  }

  pasteJson(section: EditorSection): void {
    let questions: unknown[];
    try {
      const parsed = JSON.parse(section.pasteText);
      if (!Array.isArray(parsed) || parsed.length === 0) throw new Error();
      questions = parsed;
    } catch {
      this.patchSection(section.id, { pasteError: 'Invalid JSON. Must be a non-empty array.' });
      return;
    }
    this.examService.addBankQuestions(this.bankId, section.id, questions as never[]).subscribe({
      next: () => this.load(),
      error: (err) => {
        this.patchSection(section.id, {
          pasteError: err?.error?.detail || 'Could not add those questions.',
        });
      },
    });
  }

  addQuestion(section: EditorSection): void {
    this.addingQuestion.set({ ...this.addingQuestion(), [section.id]: true });
    this.examService.addBankQuestions(this.bankId, section.id, [DEFAULT_MCQ_PAYLOAD]).subscribe({
      next: () => {
        this.addingQuestion.set({ ...this.addingQuestion(), [section.id]: false });
        this.load();
      },
      error: (err) => {
        this.addingQuestion.set({ ...this.addingQuestion(), [section.id]: false });
        alert(err?.error?.detail || 'Could not add a question.');
      },
    });
  }

  toggleExpand(d: QuestionDraft): void {
    this.expanded.set({ ...this.expanded(), [d.id]: !this.expanded()[d.id] });
  }

  replaceDraft(updated: QuestionDraft): void {
    this.sections.update((list) =>
      list.map((s) => ({
        ...s,
        drafts: s.drafts.map((d) => (d.id === updated.id ? updated : d)),
      })),
    );
  }

  private currentDraft(id: number): QuestionDraft | undefined {
    for (const s of this.sections()) {
      const d = s.drafts.find((q) => q.id === id);
      if (d) return d;
    }
    return undefined;
  }

  private sectionOf(questionId: number): EditorSection | undefined {
    return this.sections().find((s) => s.drafts.some((d) => d.id === questionId));
  }

  save(clicked: QuestionDraft): void {
    const d = this.currentDraft(clicked.id) ?? clicked;
    const section = this.sectionOf(d.id);
    if (!section) return;
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
      .updateBankQuestion(this.bankId, section.id, d.id, {
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
    const section = this.sectionOf(d.id);
    if (!section) return;
    if (!confirm('Delete this question? This cannot be undone.')) return;
    this.examService.deleteBankQuestion(this.bankId, section.id, d.id).subscribe({
      next: () =>
        this.patchSection(section.id, {
          drafts: section.drafts.filter((x) => x.id !== d.id),
        }),
      error: (err) => this.setError(d.id, err?.error?.detail || 'Delete failed.'),
    });
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

  patchSection(id: string, patch: Partial<EditorSection>): void {
    this.sections.update((list) => list.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }

  private setFlag(sig: WritableSignal<Record<number, boolean>>, id: number, value: boolean): void {
    sig.set({ ...sig(), [id]: value });
  }

  private setError(id: number, message: string): void {
    this.draftError.set({ ...this.draftError(), [id]: message });
  }
}
