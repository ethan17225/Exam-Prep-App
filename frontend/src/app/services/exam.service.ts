import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
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

export interface QuestionTypeCounts {
  mcq: number;
  sata: number;
  fib: number;
}

/** Classify a question the same way as take-exam and server grading. */
export function classifyQuestionType(q: { type: string; options?: string[] | null }): 'MCQ' | 'SATA' | 'FIB' {
  const t = (q.type ?? '').trim();
  if (t === 'SATA') return 'SATA';
  if (t === 'FIB' || t === 'Fill-in-the-blank' || !q.options || q.options.length === 0) return 'FIB';
  return 'MCQ';
}

export function countQuestionTypes<T extends { type: string; options?: string[] | null }>(questions: T[]): QuestionTypeCounts {
  const out: QuestionTypeCounts = { mcq: 0, sata: 0, fib: 0 };
  for (const q of questions) {
    const g = classifyQuestionType(q);
    if (g === 'MCQ') out.mcq += 1;
    else if (g === 'SATA') out.sata += 1;
    else out.fib += 1;
  }
  return out;
}

export interface Course {
  id: string;
  name: string;
  created_at: string;
}

export interface DocumentItem {
  filename: string;
  title: string;
  pdf_url: string;
  html_url: string | null;
  size_bytes: number;
  course_id: string | null;
  course_name: string | null;
}

export interface DocumentContent {
  title: string;
  html: string;
}

export interface ExamSummary {
  id: string;
  title: string;
  course_id: string | null;
  course_name: string | null;
  time_limit_minutes: number | null;
  total_questions: number;
  mcq_count: number;
  sata_count: number;
  fib_count: number;
  created_at: string;
}

export interface ExamDetail {
  id: string;
  title: string;
  course_name?: string | null;
  time_limit_minutes?: number | null;
  questions: Question[];
}

export interface AnswerSubmission {
  question_number: number;
  answer: string | string[];
  fib_correct?: boolean | null;
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
  started_at: string | null;
  saved_at: string;
}

export interface AdminDashboardItem {
  id: string;
  exam_id: string;
  exam_title: string;
  mode: string;
  total_questions: number;
  answered_count: number;
  remaining_count: number;
  correct_count: number;
  wrong_count: number;
  score_percent: number;
  started_at: string | null;
  saved_at: string;
  seconds_since_last_answer: number;
  seconds_since_start: number | null;
  remaining_seconds: number;
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

  createExam(title: string, questions: Question[], courseId?: string, timeLimitMinutes?: number | null): Observable<{ exam_id: string; total_questions: number }> {
    const body: Record<string, unknown> = { title, questions };
    if (courseId) body['course_id'] = courseId;
    if (timeLimitMinutes) body['time_limit_minutes'] = timeLimitMinutes;
    return this.http.post<{ exam_id: string; total_questions: number }>(`${this.base}/exams`, body);
  }

  listExams(courseId?: string): Observable<ExamSummary[]> {
    let params = new HttpParams();
    if (courseId) params = params.set('course_id', courseId);
    return this.http.get<ExamSummary[]>(`${this.base}/exams`, { params });
  }

  listCourses(): Observable<Course[]> {
    return this.http.get<Course[]>(`${this.base}/courses`);
  }

  createCourse(name: string): Observable<Course> {
    return this.http.post<Course>(`${this.base}/courses`, { name });
  }

  listDocuments(courseId?: string): Observable<DocumentItem[]> {
    let params = new HttpParams();
    if (courseId) params = params.set('course_id', courseId);
    return this.http.get<DocumentItem[]>(`${this.base}/documents`, { params });
  }

  getDocumentContent(docUrl: string): Observable<DocumentContent> {
    const params = new HttpParams().set('path', docUrl);
    return this.http.get<DocumentContent>(`${this.base}/documents/html`, { params });
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

  updateTimeLimit(id: string, timeLimitMinutes: number | null): Observable<ExamSummary> {
    return this.http.patch<ExamSummary>(`${this.base}/exams/${id}/time-limit`, { time_limit_minutes: timeLimitMinutes });
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

  getAdminDashboard(): Observable<AdminDashboardItem[]> {
    return this.http.get<AdminDashboardItem[]>(`${this.base}/admin/dashboard`);
  }
}
