import { Component, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ExamService } from '../../services/exam.service';

@Component({
  selector: 'app-upload',
  imports: [FormsModule],
  templateUrl: './upload.html',
  styleUrl: './upload.scss',
})
export class UploadPage {
  title = signal('');
  jsonText = signal('');
  error = signal('');
  loading = signal(false);

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      this.jsonText.set(reader.result as string);
      if (!this.title()) {
        const name = file.name.replace(/\.json$/i, '');
        this.title.set(name);
      }
    };
    reader.readAsText(file);
  }

  submit(): void {
    this.error.set('');
    const titleVal = this.title().trim();
    const jsonVal = this.jsonText().trim();

    if (!titleVal) {
      this.error.set('Please enter an exam title.');
      return;
    }
    if (!jsonVal) {
      this.error.set('Please paste or upload a JSON file.');
      return;
    }

    let questions: unknown[];
    try {
      questions = JSON.parse(jsonVal);
      if (!Array.isArray(questions) || questions.length === 0) throw new Error();
    } catch {
      this.error.set('Invalid JSON. Must be a non-empty array of question objects.');
      return;
    }

    this.loading.set(true);
    this.examService.createExam(titleVal, questions as never[]).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/exams']);
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || 'Failed to create exam.');
      },
    });
  }
}
