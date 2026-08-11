import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

/** Structured options for MATRIX questions: a grid of rows x columns. */
export interface MatrixOptions {
  rows: string[];
  columns: string[];
}

/** One dropdown blank in a CLOZE question. */
export interface ClozeBlank {
  label: string;
  choices: string[];
}

/** One category (drop zone) in a BOWTIE question. */
export interface BowtieCategory {
  name: string;
  count: number;
  choices: string[];
}

/** A clickable region on a HOTSPOT image; coordinates are percentages (0-100). */
export interface HotspotRegion {
  id: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export type QuestionOptions =
  | string[]
  | MatrixOptions
  | { blanks: ClozeBlank[] }
  | { categories: BowtieCategory[] }
  | { tokens: string[] }
  | { regions: HotspotRegion[] }
  | null;

export type AnswerValue = string | string[] | number[] | Record<string, string[]>;

/** A paragraph of case-study text inside a section. */
export interface TextBlock {
  type: 'text';
  text: string;
}

/** A bulleted list inside a section. */
export interface ListBlock {
  type: 'list';
  items: string[];
}

/** A data table (labs, vitals, medication records) inside a section. */
export interface TableBlock {
  type: 'table';
  caption?: string;
  headers?: string[];
  rows?: string[][];
}

export type SectionBlock = TextBlock | ListBlock | TableBlock;

/**
 * One tab of supporting patient data (e.g. "Nurses' Notes", "Laboratory Results").
 * A question with more than one section renders as a tabbed chart.
 */
export interface QuestionSection {
  title: string;
  blocks: SectionBlock[];
}

export interface Question {
  id?: number;
  number: number;
  topic: string;
  type: string;
  question: string;
  sections?: QuestionSection[] | null;
  options?: QuestionOptions;
  answer?: AnswerValue;
  rationale?: string;
  image?: string | null;
}

export type QuestionKind =
  | 'MCQ'
  | 'SATA'
  | 'FIB'
  | 'MATRIX'
  | 'CLOZE'
  | 'BOWTIE'
  | 'RANKING'
  | 'HIGHLIGHT'
  | 'HOTSPOT';

export const ADVANCED_KINDS: QuestionKind[] = ['MATRIX', 'CLOZE', 'BOWTIE', 'RANKING', 'HIGHLIGHT', 'HOTSPOT'];

export interface QuestionTypeCounts {
  mcq: number;
  sata: number;
  fib: number;
  other: number;
}

/** Classify a question the same way as take-exam and server grading. */
export function classifyQuestionType(q: { type: string; options?: QuestionOptions | null }): QuestionKind {
  const t = (q.type ?? '').trim().toUpperCase();
  if ((ADVANCED_KINDS as string[]).includes(t)) return t as QuestionKind;
  if (t === 'SATA') return 'SATA';
  if (t === 'FIB' || t === 'FILL-IN-THE-BLANK' || !q.options || (Array.isArray(q.options) && q.options.length === 0)) {
    return 'FIB';
  }
  return 'MCQ';
}

export function countQuestionTypes<T extends { type: string; options?: QuestionOptions | null }>(questions: T[]): QuestionTypeCounts {
  const out: QuestionTypeCounts = { mcq: 0, sata: 0, fib: 0, other: 0 };
  for (const q of questions) {
    const g = classifyQuestionType(q);
    if (g === 'MCQ') out.mcq += 1;
    else if (g === 'SATA') out.sata += 1;
    else if (g === 'FIB') out.fib += 1;
    else out.other += 1;
  }
  return out;
}

// ── Structured option accessors ─────────────────────────────────

export function matrixRows(q: { options?: QuestionOptions }): string[] {
  const o = q.options as MatrixOptions | undefined;
  return o && !Array.isArray(o) && 'rows' in o ? o.rows : [];
}

export function matrixColumns(q: { options?: QuestionOptions }): string[] {
  const o = q.options as MatrixOptions | undefined;
  return o && !Array.isArray(o) && 'columns' in o ? o.columns : [];
}

export function clozeBlanks(q: { options?: QuestionOptions }): ClozeBlank[] {
  const o = q.options as { blanks?: ClozeBlank[] } | undefined;
  return o && !Array.isArray(o) && Array.isArray(o.blanks) ? o.blanks : [];
}

export function bowtieCategories(q: { options?: QuestionOptions }): BowtieCategory[] {
  const o = q.options as { categories?: BowtieCategory[] } | undefined;
  return o && !Array.isArray(o) && Array.isArray(o.categories) ? o.categories : [];
}

export function highlightTokens(q: { options?: QuestionOptions }): string[] {
  const o = q.options as { tokens?: string[] } | undefined;
  return o && !Array.isArray(o) && Array.isArray(o.tokens) ? o.tokens : [];
}

export function hotspotRegions(q: { options?: QuestionOptions }): HotspotRegion[] {
  const o = q.options as { regions?: HotspotRegion[] } | undefined;
  return o && !Array.isArray(o) && Array.isArray(o.regions) ? o.regions : [];
}

export function rankingItems(q: { options?: QuestionOptions }): string[] {
  return Array.isArray(q.options) ? q.options : [];
}

/** Human-readable rendering of any answer shape, for review screens. */
export function formatAnswerForDisplay(
  q: { type: string; options?: QuestionOptions | null },
  ans: AnswerValue | null | undefined,
): string {
  if (ans === null || ans === undefined) return '—';
  const kind = classifyQuestionType(q);

  if (kind === 'MATRIX' && typeof ans === 'object' && !Array.isArray(ans)) {
    const rows = matrixRows(q);
    const parts = Object.entries(ans as Record<string, string[]>)
      .filter(([, v]) => Array.isArray(v) && v.length > 0)
      .map(([k, v]) => {
        const idx = Number(k);
        const label = Number.isFinite(idx) && rows[idx] !== undefined ? rows[idx] : k;
        return `${label} → ${v.join(', ')}`;
      });
    return parts.length ? parts.join(' | ') : '—';
  }

  if (kind === 'BOWTIE' && typeof ans === 'object' && !Array.isArray(ans)) {
    const parts = Object.entries(ans as Record<string, string[]>)
      .filter(([, v]) => Array.isArray(v) && v.length > 0)
      .map(([k, v]) => `${k}: ${v.join(', ')}`);
    return parts.length ? parts.join(' | ') : '—';
  }

  if (kind === 'CLOZE' && Array.isArray(ans)) {
    const blanks = clozeBlanks(q);
    const parts = (ans as string[]).map((v, i) => {
      const label = blanks[i]?.label;
      return label ? `${label}: ${v || '—'}` : String(v || '—');
    });
    return parts.length ? parts.join(' | ') : '—';
  }

  if (kind === 'HIGHLIGHT' && Array.isArray(ans)) {
    const tokens = highlightTokens(q);
    const parts = (ans as number[]).map((i) => tokens[Number(i)] ?? String(i));
    return parts.length ? parts.join('; ') : '—';
  }

  if (kind === 'HOTSPOT') {
    const region = hotspotRegions(q).find((r) => r.id === String(ans));
    return region?.label ?? String(ans);
  }

  if (kind === 'RANKING' && Array.isArray(ans)) {
    return ans.length ? (ans as string[]).join(' → ') : '—';
  }

  if (Array.isArray(ans)) return ans.length ? ans.join(', ') : '—';
  return String(ans) || '—';
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
  other_count?: number;
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
  answer: AnswerValue;
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
  sections?: QuestionSection[] | null;
  options?: QuestionOptions;
  image?: string | null;
  user_answer: AnswerValue | null;
  correct_answer: AnswerValue;
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
  answers: Record<string, AnswerValue>;
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
  answers: Record<string, AnswerValue>;
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

  // ── Question editing ─────────────────────────────────────────

  addQuestion(examId: string, question: Partial<Question>): Observable<Question> {
    return this.http.post<Question>(`${this.base}/exams/${examId}/questions`, question);
  }

  updateQuestion(examId: string, questionId: number, patch: Partial<Question>): Observable<Question> {
    return this.http.patch<Question>(`${this.base}/exams/${examId}/questions/${questionId}`, patch);
  }

  deleteQuestion(examId: string, questionId: number): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/exams/${examId}/questions/${questionId}`);
  }

  uploadQuestionImage(questionId: number, file: File): Observable<{ image: string }> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<{ image: string }>(`${this.base}/questions/${questionId}/image`, form);
  }

  deleteQuestionImage(questionId: number): Observable<{ image: null }> {
    return this.http.delete<{ image: null }>(`${this.base}/questions/${questionId}/image`);
  }
}
