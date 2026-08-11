import { Component, computed, input } from '@angular/core';
import { QuestionSectionsComponent } from '../question-sections/question-sections';
import {
  AnswerValue,
  QuestionKind,
  QuestionResult,
  classifyQuestionType,
  formatAnswerForDisplay,
} from '../../services/exam.service';

/**
 * One reviewed question card — shared by the results and history-detail pages so the
 * same attempt can never render differently on the two screens.
 */
@Component({
  selector: 'app-answer-review',
  imports: [QuestionSectionsComponent],
  templateUrl: './answer-review.html',
  styleUrl: './answer-review.scss',
})
export class AnswerReviewComponent {
  question = input.required<QuestionResult>();

  kind = computed<QuestionKind>(() => classifyQuestionType(this.question()));
  isSata = computed(() => this.kind() === 'SATA');
  isAdvanced = computed(() => {
    const k = this.kind();
    return k !== 'MCQ' && k !== 'SATA' && k !== 'FIB';
  });

  options = computed<string[]>(() => {
    const o = this.question().options;
    return Array.isArray(o) ? o : [];
  });

  /** Only MCQ/SATA render a letter-based option list. */
  showOptionList = computed(() => {
    const k = this.kind();
    return (k === 'MCQ' || k === 'SATA') && this.options().length > 0;
  });

  userAnswerText = computed(() =>
    formatAnswerForDisplay(this.question(), this.question().user_answer),
  );
  correctAnswerText = computed(() =>
    formatAnswerForDisplay(this.question(), this.question().correct_answer),
  );

  private userLetters = computed(() => this.answerLetters(this.question().user_answer));
  private correctLetters = computed(() => this.answerLetters(this.question().correct_answer));

  isUserPick(opt: string): boolean {
    return this.userLetters().has(this.optionLetter(opt));
  }

  isCorrectOpt(opt: string): boolean {
    return this.correctLetters().has(this.optionLetter(opt));
  }

  /** First answer letter (A–Z) from an option line, e.g. "A. Text" or "  B) ..." */
  private optionLetter(opt: string): string {
    const t = opt.trim();
    const m = t.match(/^([A-Z])\s*[.)]/i) ?? t.match(/^([A-Z])\b/i);
    return (m ? m[1] : t.charAt(0)).toUpperCase();
  }

  /** Letters in an answer value (handles arrays, comma strings, and a single letter). */
  private answerLetters(ans: AnswerValue | null | undefined): Set<string> {
    if (ans === null || ans === undefined) return new Set();
    if (Array.isArray(ans)) {
      return new Set(ans.map((x) => String(x).trim().toUpperCase().slice(0, 1)).filter(Boolean));
    }
    const s = String(ans).trim();
    if (!s) return new Set();
    return new Set(
      s
        .split(',')
        .map((x) => x.trim().toUpperCase().slice(0, 1))
        .filter(Boolean),
    );
  }
}
