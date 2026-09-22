import { Component, OnInit, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { httpErrorDetail, ExamService, QuestionBankSummary } from '../../services/exam.service';

@Component({
  selector: 'app-banks',
  imports: [FormsModule],
  templateUrl: './banks.html',
  styleUrl: './banks.scss',
})
export class BanksPage implements OnInit {
  banks = signal<QuestionBankSummary[]>([]);
  loading = signal(true);
  loadError = signal('');
  newTitle = signal('');
  creating = signal(false);
  createError = signal('');
  deleteError = signal<Record<string, string>>({});

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.listBanks().subscribe({
      next: (data) => {
        this.banks.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(httpErrorDetail(err) || 'Failed to load question banks.');
      },
    });
  }

  create(): void {
    const title = this.newTitle().trim();
    if (!title) {
      this.createError.set('Enter a title for the new bank.');
      return;
    }
    this.creating.set(true);
    this.createError.set('');
    this.examService.createBank(title).subscribe({
      next: (bank) => this.router.navigate(['/banks', bank.id]),
      error: (err) => {
        this.creating.set(false);
        this.createError.set(httpErrorDetail(err) || 'Could not create the bank.');
      },
    });
  }

  open(bank: QuestionBankSummary): void {
    this.router.navigate(['/banks', bank.id]);
  }

  remove(bank: QuestionBankSummary): void {
    if (
      !confirm(
        `Delete “${bank.title}” and all of its questions? Linked exams must be deleted first.`,
      )
    )
      return;
    this.examService.deleteBank(bank.id).subscribe({
      next: () => this.load(),
      error: (err) => {
        this.deleteError.set({
          ...this.deleteError(),
          [bank.id]: httpErrorDetail(err) || 'Delete failed.',
        });
      },
    });
  }
}
