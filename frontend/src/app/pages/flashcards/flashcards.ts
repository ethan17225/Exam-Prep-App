import { Component, HostListener, OnInit, signal, computed } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ExamService, Question } from '../../services/exam.service';

@Component({
  selector: 'app-flashcards',
  imports: [],
  templateUrl: './flashcards.html',
  styleUrl: './flashcards.scss',
})
export class FlashcardsPage implements OnInit {
  examTitle = signal('');
  questions = signal<Question[]>([]);
  currentIndex = signal(0);
  flipped = signal(false);
  loading = signal(true);
  error = signal('');

  private examId = '';

  total = computed(() => this.questions().length);
  currentQuestion = computed(() => {
    const list = this.questions();
    const i = this.currentIndex();
    return list.length > 0 && i >= 0 && i < list.length ? list[i] : null;
  });

  progressLabel = computed(() => {
    const t = this.total();
    if (t === 0) return '';
    return `${this.currentIndex() + 1} / ${t}`;
  });

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    this.examId = this.route.snapshot.paramMap.get('id')!;
    const countParam = Number(this.route.snapshot.queryParamMap.get('count'));
    const shuffle = this.route.snapshot.queryParamMap.get('shuffle') !== 'false';

    this.examService.getExam(this.examId, true).subscribe({
      next: (exam) => {
        this.examTitle.set(exam.title);
        let list = [...exam.questions];
        if (shuffle) list = this.shuffle(list);
        if (Number.isFinite(countParam) && countParam > 0) {
          list = list.slice(0, Math.min(countParam, list.length));
        }
        this.questions.set(list);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Could not load this exam.');
      },
    });
  }

  @HostListener('document:keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    if (this.loading() || this.total() === 0) return;
    if (ev.key === 'ArrowLeft') {
      ev.preventDefault();
      this.prev();
    } else if (ev.key === 'ArrowRight') {
      ev.preventDefault();
      this.next();
    } else if (ev.key === ' ' || ev.key === 'Enter') {
      ev.preventDefault();
      this.toggleFlip();
    }
  }

  private shuffle<T>(arr: T[]): T[] {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  toggleFlip(): void {
    if (this.total() === 0) return;
    this.flipped.update((v) => !v);
  }

  prev(): void {
    if (this.currentIndex() <= 0) return;
    this.flipped.set(false);
    this.currentIndex.update((i) => i - 1);
  }

  next(): void {
    if (this.currentIndex() >= this.total() - 1) return;
    this.flipped.set(false);
    this.currentIndex.update((i) => i + 1);
  }

  backToExams(): void {
    this.router.navigate(['/exams']);
  }

  isTextQuestion(q: Question): boolean {
    return !q.options?.length || q.type === 'FIB' || q.type === 'Fill-in-the-blank';
  }

  formatAnswer(q: Question): string {
    const a = q.answer;
    if (a === undefined || a === null) return '—';
    if (Array.isArray(a)) return a.join(', ');
    return String(a);
  }
}
