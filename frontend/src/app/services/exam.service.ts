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

export const ADVANCED_KINDS: QuestionKind[] = [
  'MATRIX',
  'CLOZE',
  'BOWTIE',
  'RANKING',
  'HIGHLIGHT',
  'HOTSPOT',
];

export interface QuestionTypeCounts {
  mcq: number;
  sata: number;
  fib: number;
  other: number;
}

/** Classify a question the same way as take-exam and server grading. */
export function classifyQuestionType(q: {
  type: string;
  options?: QuestionOptions | null;
}): QuestionKind {
  const t = (q.type ?? '').trim().toUpperCase();
  if ((ADVANCED_KINDS as string[]).includes(t)) return t as QuestionKind;
  if (t === 'SATA') return 'SATA';
  if (
    t === 'FIB' ||
    t === 'FILL-IN-THE-BLANK' ||
    !q.options ||
    (Array.isArray(q.options) && q.options.length === 0)
  ) {
    return 'FIB';
  }
  return 'MCQ';
}

export function countQuestionTypes<T extends { type: string; options?: QuestionOptions | null }>(
  questions: T[],
): QuestionTypeCounts {
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

// ── Shared page helpers ─────────────────────────────────────────

/** One date format app-wide: locale date + time. */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

/** Compact human duration: "1h 5m", "5m 3s", "42s". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (hrs > 0) return `${hrs}h ${mins}m`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

/** HH:MM:SS, for countdown timers. */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

/** Fisher–Yates, non-mutating. */
export function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/**
 * Where a per-topic score stops reading as weak. Presentation only, and
 * deliberately not a pass grade: a topic spans many exams, each with its own
 * threshold, so there is no single exam rule to apply to it.
 */
export const TOPIC_MASTERY_THRESHOLD = 72;

/** Answered-so-far percentage for an in-progress attempt. */
export function progressPercent(record: {
  answered_count: number;
  total_questions: number;
}): number {
  if (record.total_questions === 0) return 0;
  return Math.round((record.answered_count / record.total_questions) * 100);
}

/** Kind from the type string alone — for editors where the type dropdown, not the options shape, is authoritative. */
export function kindFromType(type: string): QuestionKind {
  const t = (type ?? '').trim().toUpperCase();
  if ((ADVANCED_KINDS as string[]).includes(t)) return t as QuestionKind;
  if (t === 'SATA') return 'SATA';
  if (t === 'FIB' || t === 'FILL-IN-THE-BLANK') return 'FIB';
  return 'MCQ';
}

// ── Client-side grading ─────────────────────────────────────────
// Port of backend/src/grading/service.py (grade_question) + utils.py. Practice-mode
// feedback must agree with the graded score, so any change there changes here.

/** Unordered comparison — SATA, HIGHLIGHT. Accepts a list or a comma-separated string. */
function normStrSet(values: unknown): Set<string> {
  if (values === null || values === undefined) return new Set();
  if (Array.isArray(values)) {
    return new Set(values.map((v) => String(v).trim()).filter(Boolean));
  }
  const s = String(values).trim();
  return new Set(
    s
      ? s
          .split(',')
          .map((p) => p.trim())
          .filter(Boolean)
      : [],
  );
}

/** Ordered comparison — CLOZE, RANKING. */
function normStrList(values: unknown): string[] {
  if (values === null || values === undefined) return [];
  if (Array.isArray(values)) return values.map((v) => String(v).trim());
  return [String(values).trim()];
}

/** MATRIX/BOWTIE answers: key -> set of selections. */
function groupedAnswerMap(value: unknown): Record<string, Set<string>> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const out: Record<string, Set<string>> = {};
  for (const [k, v] of Object.entries(value)) {
    const selections = normStrSet(v);
    if (selections.size) out[String(k).trim()] = selections;
  }
  return out;
}

function setsEqual(a: Set<string>, b: Set<string>): boolean {
  return a.size === b.size && [...a].every((x) => b.has(x));
}

/**
 * True when `userAnswer` grades correct under the backend's rules.
 * FIB self-marking (practice mode) is the caller's concern — this implements the
 * server's fallback FIB matching (float equality, then fuzzy substring).
 */
export function isAnswerCorrect(q: Question, userAnswer: AnswerValue | null | undefined): boolean {
  const expected = q.answer;
  if (expected === undefined || expected === null) return false;
  const kind = classifyQuestionType(q);

  if (kind === 'MATRIX' || kind === 'BOWTIE') {
    const user = groupedAnswerMap(userAnswer);
    const exp = groupedAnswerMap(expected);
    const keys = Object.keys(exp);
    if (keys.length !== Object.keys(user).length) return false;
    return keys.every((k) => user[k] !== undefined && setsEqual(exp[k], user[k]));
  }

  if (kind === 'CLOZE') {
    const user = normStrList(Array.isArray(userAnswer) ? userAnswer : null);
    const exp = normStrList(expected);
    return (
      user.length === exp.length && user.every((u, i) => u.toLowerCase() === exp[i].toLowerCase())
    );
  }

  if (kind === 'RANKING') {
    const user = normStrList(Array.isArray(userAnswer) ? userAnswer : null);
    const exp = normStrList(expected);
    return user.length === exp.length && user.every((u, i) => u === exp[i]);
  }

  if (kind === 'HIGHLIGHT') {
    return setsEqual(normStrSet(userAnswer), normStrSet(expected));
  }

  if (kind === 'HOTSPOT') {
    const user = String(userAnswer ?? '').trim();
    return user !== '' && user === String(expected).trim();
  }

  if (kind === 'SATA') {
    return setsEqual(normStrSet(expected), normStrSet(userAnswer));
  }

  if (kind === 'FIB') {
    const user = String(userAnswer ?? '')
      .trim()
      .toLowerCase();
    const exp = String(expected).trim().toLowerCase();
    const uf = Number(user);
    const ef = Number(exp);
    if (user !== '' && exp !== '' && Number.isFinite(uf) && Number.isFinite(ef)) return uf === ef;
    return (
      user === exp ||
      (user.length >= 3 && exp.includes(user)) ||
      (exp.length >= 3 && user.includes(exp))
    );
  }

  return String(userAnswer ?? '').trim() === String(expected).trim();
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
  /** The passing score as a percentage, 1-100. Chosen per exam at upload. */
  pass_grade: number;
  /** Practice mode reveals the answer key, so a graded exam has this off. */
  allow_practice: boolean;
  /** Only the owner may rename, edit, delete or re-flag an exam. */
  is_owner: boolean;
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
  pass_grade: number;
  /**
   * Whether `answer`/`rationale` are present on the questions below. The server
   * withholds them unless you own the exam or practice is allowed, so never
   * infer it from a field being missing.
   */
  answers_included: boolean;
  allow_practice: boolean;
  is_owner: boolean;
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

/**
 * What `GET /api/history` returns. The heavy `results` blob is deliberately
 * absent from the list — fetch a single record for that.
 */
export interface ExamResultSummary {
  id: string;
  exam_id: string;
  exam_title: string;
  score: number;
  correct: number;
  total: number;
  passed: boolean;
  /**
   * The threshold this attempt was graded against, copied onto the record at
   * submit. Use it rather than a constant — an instructor changing the exam's
   * pass grade must not relabel attempts that are already graded.
   */
  pass_grade: number;
  time_spent_seconds: number;
  mode: string;
  /** Submitted after the time limit; graded against the last pre-deadline save. */
  over_time: boolean;
  taken_at: string;
}

export interface ExamResult extends ExamResultSummary {
  results: QuestionResult[];
}

/** Per-topic performance, aggregated server-side across every attempt. */
export interface TopicStat {
  topic: string;
  score: number;
  correct: number;
  total: number;
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
  /** The live exam's current pass mark, for colouring the partial score. */
  pass_grade: number;
  /** Which student this attempt belongs to. Instructor-only view. */
  student_name: string | null;
  student_email: string | null;
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

// ── Instructor analytics ────────────────────────────────────────

/** One student plus their aggregates, as the Students page lists them. */
export interface StudentItem {
  id: string;
  display_name: string | null;
  email: string;
  avatar: string | null;
  attempts: number;
  exam_attempts: number;
  practice_attempts: number;
  average_score: number;
  best_score: number;
  pass_rate: number;
  total_seconds: number;
  in_progress_count: number;
  last_attempt_at: string | null;
  joined_at: string;
}

/** An attempt in the instructor's drill-down; no `results` blob by design. */
export interface StudentAttempt {
  id: string;
  exam_id: string;
  exam_title: string;
  score: number;
  correct: number;
  total: number;
  passed: boolean;
  pass_grade: number;
  mode: string;
  over_time: boolean;
  time_spent_seconds: number;
  taken_at: string;
}

export interface StudentDetail {
  student: StudentItem;
  recent_attempts: StudentAttempt[];
  topic_stats: TopicStat[];
}

export interface ExamRollup {
  exam_id: string;
  exam_title: string;
  pass_grade: number;
  attempts: number;
  students: number;
  average_score: number;
  pass_rate: number;
  last_attempt_at: string | null;
}

export interface DailyPoint {
  day: string;
  attempts: number;
  average_score: number;
}

export interface InstructorOverview {
  student_count: number;
  exam_count: number;
  attempts: number;
  recent_attempts: number;
  live_now: number;
  average_score: number;
  pass_rate: number;
  total_seconds: number;
  invite_code: string | null;
  attempts_per_day: DailyPoint[];
  /** Ten 10-point score bands, low to high. Always exactly ten entries. */
  score_buckets: number[];
  passed_count: number;
  failed_count: number;
  exam_rollups: ExamRollup[];
  topic_stats: TopicStat[];
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

  createExam(
    title: string,
    questions: Question[],
    passGrade: number,
    courseId?: string,
    timeLimitMinutes?: number | null,
  ): Observable<{ exam_id: string; total_questions: number }> {
    const body: Record<string, unknown> = { title, questions, pass_grade: passGrade };
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

  getExam(id: string, includeAnswers = false): Observable<ExamDetail> {
    const params = includeAnswers ? '?include_answers=true' : '';
    return this.http.get<ExamDetail>(`${this.base}/exams/${id}${params}`);
  }

  submitExam(payload: SubmissionPayload): Observable<ExamResult> {
    return this.http.post<ExamResult>(`${this.base}/exams/${payload.exam_id}/submit`, payload);
  }

  getHistory(): Observable<ExamResultSummary[]> {
    return this.http.get<ExamResultSummary[]>(`${this.base}/history`);
  }

  getTopicStats(): Observable<TopicStat[]> {
    return this.http.get<TopicStat[]>(`${this.base}/history/topic-stats`);
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
    return this.http.patch<ExamSummary>(`${this.base}/exams/${id}/time-limit`, {
      time_limit_minutes: timeLimitMinutes,
    });
  }

  updateAllowPractice(id: string, allowPractice: boolean): Observable<ExamSummary> {
    return this.http.patch<ExamSummary>(`${this.base}/exams/${id}/allow-practice`, {
      allow_practice: allowPractice,
    });
  }

  updatePassGrade(id: string, passGrade: number): Observable<ExamSummary> {
    return this.http.patch<ExamSummary>(`${this.base}/exams/${id}/pass-grade`, {
      pass_grade: passGrade,
    });
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

  deleteInProgressByExam(examId: string, mode = 'exam'): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${this.base}/in-progress/by-exam/${examId}?mode=${mode}`,
    );
  }

  getAdminDashboard(): Observable<AdminDashboardItem[]> {
    return this.http.get<AdminDashboardItem[]>(`${this.base}/admin/dashboard`);
  }

  // ── Instructor analytics ─────────────────────────────────────
  //
  // All three are instructor-only and scoped server-side to the caller's own
  // students, so nothing here takes an instructor id.

  getInstructorOverview(): Observable<InstructorOverview> {
    return this.http.get<InstructorOverview>(`${this.base}/admin/overview`);
  }

  getStudents(): Observable<StudentItem[]> {
    return this.http.get<StudentItem[]>(`${this.base}/admin/students`);
  }

  getStudentDetail(studentId: string): Observable<StudentDetail> {
    return this.http.get<StudentDetail>(`${this.base}/admin/students/${studentId}`);
  }

  // ── Question editing ─────────────────────────────────────────

  addQuestion(examId: string, question: Partial<Question>): Observable<Question> {
    return this.http.post<Question>(`${this.base}/exams/${examId}/questions`, question);
  }

  updateQuestion(
    examId: string,
    questionId: number,
    patch: Partial<Question>,
  ): Observable<Question> {
    return this.http.patch<Question>(`${this.base}/exams/${examId}/questions/${questionId}`, patch);
  }

  deleteQuestion(examId: string, questionId: number): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${this.base}/exams/${examId}/questions/${questionId}`,
    );
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
