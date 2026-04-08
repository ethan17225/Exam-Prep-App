import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Question {
  number: number;
  topic: string;
  type: string;
  question: string;
  options?: string[];
  answer?: string | string[];
  rationale?: string;
}

export interface ExamSummary {
  id: string;
  title: string;
  total_questions: number;
  created_at: string;
}

export interface ExamDetail {
  id: string;
  title: string;
  questions: Question[];
}

export interface AnswerSubmission {
  question_number: number;
  answer: string | string[];
}

export interface SubmissionPayload {
  exam_id: string;
  answers: AnswerSubmission[];
  time_spent_seconds: number;
  mode?: string;
  question_numbers?: number[];
}

export interface QuestionResult {
  question_number: number;
  question: string;
  topic: string;
  type: string;
  options?: string[];
  user_answer: string | string[] | null;
  correct_answer: string | string[];
  is_correct: boolean;
  rationale: string;
}

export interface ExamResult {
  id: string;
  exam_id: string;
  exam_title: string;
  score: number;
  correct: number;
  total: number;
  passed: boolean;
  time_spent_seconds: number;
  mode: string;
  results: QuestionResult[];
  taken_at: string;
}

export interface InProgressExam {
  id: string;
  exam_id: string;
  exam_title: string;
  mode: string;
  answers: Record<string, string | string[]>;
  flagged: number[];
  question_order: number[];
  remaining_seconds: number;
  current_page: number;
  total_questions: number;
  answered_count: number;
  saved_at: string;
}

export interface SaveProgressPayload {
  exam_id: string;
  mode: string;
  answers: Record<string, string | string[]>;
  flagged: number[];
  question_order: number[];
  remaining_seconds: number;
  current_page: number;
}

@Injectable({ providedIn: 'root' })
export class ExamService {
  private base = '/api';

  constructor(private http: HttpClient) {}

  createExam(title: string, questions: Question[]): Observable<{ exam_id: string; total_questions: number }> {
    return this.http.post<{ exam_id: string; total_questions: number }>(`${this.base}/exams`, { title, questions });
  }

  listExams(): Observable<ExamSummary[]> {
    return this.http.get<ExamSummary[]>(`${this.base}/exams`);
  }

  getExam(id: string, includeAnswers: boolean = false): Observable<ExamDetail> {
    const params = includeAnswers ? '?include_answers=true' : '';
    return this.http.get<ExamDetail>(`${this.base}/exams/${id}${params}`);
  }

  submitExam(payload: SubmissionPayload): Observable<ExamResult> {
    return this.http.post<ExamResult>(`${this.base}/exams/${payload.exam_id}/submit`, payload);
  }

  getHistory(): Observable<ExamResult[]> {
    return this.http.get<ExamResult[]>(`${this.base}/history`);
  }

  getHistoryRecord(id: string): Observable<ExamResult> {
    return this.http.get<ExamResult>(`${this.base}/history/${id}`);
  }

  deleteHistoryRecord(id: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/history/${id}`);
  }

  deleteExam(id: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/exams/${id}`);
  }

  renameExam(id: string, title: string): Observable<ExamSummary> {
    return this.http.patch<ExamSummary>(`${this.base}/exams/${id}`, { title });
  }

  saveProgress(payload: SaveProgressPayload): Observable<InProgressExam> {
    return this.http.post<InProgressExam>(`${this.base}/in-progress`, payload);
  }

  listInProgress(): Observable<InProgressExam[]> {
    return this.http.get<InProgressExam[]>(`${this.base}/in-progress`);
  }

  getInProgress(id: string): Observable<InProgressExam> {
    return this.http.get<InProgressExam>(`${this.base}/in-progress/${id}`);
  }

  deleteInProgress(id: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/in-progress/${id}`);
  }

  deleteInProgressByExam(examId: string, mode: string = 'exam'): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/in-progress/by-exam/${examId}?mode=${mode}`);
  }
}
