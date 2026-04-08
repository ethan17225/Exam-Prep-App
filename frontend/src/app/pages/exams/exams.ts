import { Component, OnInit, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService, ExamSummary } from '../../services/exam.service';

@Component({
  selector: 'app-exams',
  imports: [FormsModule],
  templateUrl: './exams.html',
  styleUrl: './exams.scss',
})
export class ExamsPage implements OnInit {
  exams = signal<ExamSummary[]>([]);
  titleDrafts = signal<Record<string, string>>({});
  questionCounts = signal<Record<string, number>>({});
  loadingRename = signal<Record<string, boolean>>({});
  renameError = signal<Record<string, string>>({});
  menuOpen = signal<string | null>(null);
  editMode = signal<Record<string, 'rename' | 'count' | null>>({});

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.examService.listExams().subscribe((data) => {
      this.exams.set(data);
      const titleDrafts: Record<string, string> = {};
      const counts: Record<string, number> = {};
      for (const exam of data) {
        titleDrafts[exam.id] = exam.title;
        counts[exam.id] = counts[exam.id] ?? exam.total_questions;
      }
      this.titleDrafts.set(titleDrafts);
      this.questionCounts.set(counts);
    });
  }

  start(exam: ExamSummary, mode: 'exam' | 'practice'): void {
    this.menuOpen.set(null);
    const selected = this.questionCounts()[exam.id] ?? exam.total_questions;
    const count = Math.max(1, Math.min(exam.total_questions, Math.floor(selected)));
    this.router.navigate(['/exam', exam.id], { queryParams: { mode, count } });
  }

  openFlashcards(exam: ExamSummary): void {
    this.menuOpen.set(null);
    const selected = this.questionCounts()[exam.id] ?? exam.total_questions;
    const count = Math.max(1, Math.min(exam.total_questions, Math.floor(selected)));
    this.router.navigate(['/flashcards', exam.id], { queryParams: { count, shuffle: true } });
  }

  updateTitleDraft(examId: string, value: string): void {
    this.titleDrafts.set({ ...this.titleDrafts(), [examId]: value });
  }

  updateQuestionCount(exam: ExamSummary, value: string): void {
    const parsed = Number(value);
    const count = Number.isFinite(parsed) ? Math.max(1, Math.min(exam.total_questions, Math.floor(parsed))) : exam.total_questions;
    this.questionCounts.set({ ...this.questionCounts(), [exam.id]: count });
  }

  saveTitle(exam: ExamSummary, event: Event): void {
    event.stopPropagation();
    const title = (this.titleDrafts()[exam.id] ?? '').trim();
    if (!title) {
      this.renameError.set({ ...this.renameError(), [exam.id]: 'Title cannot be empty.' });
      return;
    }
    if (title === exam.title) return;

    this.loadingRename.set({ ...this.loadingRename(), [exam.id]: true });
    this.renameError.set({ ...this.renameError(), [exam.id]: '' });

    this.examService.renameExam(exam.id, title).subscribe({
      next: () => {
        this.loadingRename.set({ ...this.loadingRename(), [exam.id]: false });
        this.menuOpen.set(null);
        this.load();
      },
      error: (err) => {
        this.loadingRename.set({ ...this.loadingRename(), [exam.id]: false });
        this.renameError.set({ ...this.renameError(), [exam.id]: err?.error?.detail || 'Rename failed.' });
      },
    });
  }

  toggleMenu(examId: string, event: Event): void {
    event.stopPropagation();
    if (this.menuOpen() === examId) {
      this.menuOpen.set(null);
      this.editMode.set({ ...this.editMode(), [examId]: null });
    } else {
      this.menuOpen.set(examId);
      this.editMode.set({ ...this.editMode(), [examId]: null });
    }
  }

  pickMenuOption(examId: string, option: 'rename' | 'count'): void {
    this.editMode.set({ ...this.editMode(), [examId]: option });
  }

  closeMenu(): void {
    const current = this.menuOpen();
    if (current) {
      this.editMode.set({ ...this.editMode(), [current]: null });
    }
    this.menuOpen.set(null);
  }

  remove(id: string, event: Event): void {
    event.stopPropagation();
    this.examService.deleteExam(id).subscribe(() => this.load());
  }
}
