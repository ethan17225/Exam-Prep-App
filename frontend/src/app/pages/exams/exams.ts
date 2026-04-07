import { Component, OnInit, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ExamService, ExamSummary } from '../../services/exam.service';

@Component({
  selector: 'app-exams',
  imports: [],
  templateUrl: './exams.html',
  styleUrl: './exams.scss',
})
export class ExamsPage implements OnInit {
  exams = signal<ExamSummary[]>([]);

  constructor(
    private examService: ExamService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.examService.listExams().subscribe((data) => this.exams.set(data));
  }

  start(id: string, mode: 'exam' | 'practice'): void {
    this.router.navigate(['/exam', id], { queryParams: { mode } });
  }

  remove(id: string, event: Event): void {
    event.stopPropagation();
    this.examService.deleteExam(id).subscribe(() => this.load());
  }
}
