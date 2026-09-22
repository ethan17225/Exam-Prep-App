import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { AuthUser, UserRole } from './auth.service';

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
  id: number;
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

/** Chip order when an exam has few kinds: the three common ones, then the advanced ones. */
export const QUESTION_KINDS: QuestionKind[] = ['MCQ', 'SATA', 'FIB', ...ADVANCED_KINDS];

export interface QuestionKindCount {
  kind: QuestionKind;
  count: number;
}

/** Above this many distinct kinds, chips sort by prevalence rather than canonical order. */
const KIND_SORT_THRESHOLD = 4;

/**
 * Exact per-kind counts for the kinds a question set actually contains — unlike
 * `countQuestionTypes`, advanced kinds stay separate instead of collapsing into `other`.
 * A long strip leads with the kinds the exam is mostly made of; ties keep canonical
 * order, so the strip never reshuffles between renders.
 */
export function questionKindCounts<T extends { type: string; options?: QuestionOptions | null }>(
  questions: T[],
): QuestionKindCount[] {
  const counts = new Map<QuestionKind, number>();
  for (const q of questions) {
    const kind = classifyQuestionType(q);
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  const present = QUESTION_KINDS.filter((kind) => counts.has(kind)).map((kind) => ({
    kind,
    count: counts.get(kind)!,
  }));
  return present.length > KIND_SORT_THRESHOLD ? present.sort((a, b) => b.count - a.count) : present;
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

/**
 * Unwrap an Angular HttpErrorResponse / FastAPI body into a display string.
 * `detail` is a string for domain errors and a list of `{loc, msg}` objects
 * for 422s — interpolating the list is what printed `[object Object]`.
 */
export function httpErrorDetail(err: unknown): string {
  if (err == null) return '';
  if (typeof err === 'string') return scrubObjectString(err);
  if (typeof err !== 'object') return '';

  const boxed = err as { error?: unknown; detail?: unknown; message?: unknown };
  const body = boxed.error;
  const detail =
    body && typeof body === 'object' && body !== null && 'detail' in body
      ? (body as { detail: unknown }).detail
      : boxed.detail;
  const fromDetail = formatHttpDetail(detail);
  if (fromDetail) return fromDetail;
  if (typeof body === 'string') return scrubObjectString(body);
  if (typeof boxed.message === 'string') return scrubObjectString(boxed.message);
  return '';
}

function scrubObjectString(value: string): string {
  const t = value.trim();
  return t === '' || t === '[object Object]' ? '' : t;
}

function formatHttpDetail(detail: unknown): string {
  if (detail == null) return '';
  if (typeof detail === 'string') return scrubObjectString(detail);
  if (typeof detail === 'number' || typeof detail === 'boolean') return String(detail);
  if (Array.isArray(detail)) {
    return detail.map(formatHttpDetailItem).filter(Boolean).join(' ');
  }
  if (typeof detail === 'object') return formatHttpDetailItem(detail);
  return '';
}

function formatHttpDetailItem(item: unknown): string {
  if (item == null) return '';
  if (typeof item === 'string') return scrubObjectString(item);
  if (typeof item !== 'object') return String(item);
  if (Array.isArray(item)) return item.map(formatHttpDetailItem).filter(Boolean).join(' ');
  const o = item as Record<string, unknown>;
  if (typeof o['msg'] === 'string') {
    const loc = formatErrorLoc(o['loc']);
    return loc ? `${loc}: ${o['msg']}` : o['msg'];
  }
  if (typeof o['message'] === 'string') return o['message'];
  if (typeof o['detail'] === 'string') return o['detail'];
  return '';
}

function formatErrorLoc(loc: unknown): string {
  if (!Array.isArray(loc)) return '';
  return loc
    .filter((part) => part !== 'body' && part !== 'query' && part !== 'path')
    .map(String)
    .join('.');
}

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

/**
 * Parse an API timestamp to epoch ms.
 *
 * The backend stores naive UTC (`datetime.now()` in Docker) and serializes
 * without a `Z`. `Date.parse` then treats the value as *local*, which shifts
 * the exam clock by the browser's UTC offset (e.g. +4h in EDT) and used to
 * inflate a 20-minute timer past four hours after the first autosave.
 */
export function parseServerDate(iso: string | null | undefined): number {
  if (!iso) return NaN;
  const trimmed = iso.trim();
  if (!trimmed) return NaN;
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed) ? trimmed : `${trimmed}Z`;
  return Date.parse(normalized);
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
 * Randomize the displayed choices on one question. MCQ/SATA/ranking shuffle the
 * options array; cloze and bowtie shuffle each blank/category's choices.
 * Highlight tokens and hotspot regions stay put — order is the content.
 */
export function shuffleQuestionOptions<
  T extends { type: string; options?: QuestionOptions | null },
>(q: T): T {
  const kind = classifyQuestionType(q);
  const opts = q.options;
  if (kind === 'HIGHLIGHT' || kind === 'HOTSPOT' || kind === 'MATRIX' || kind === 'FIB') {
    return q;
  }
  if (Array.isArray(opts) && opts.length > 1) {
    return { ...q, options: shuffle(opts) };
  }
  if (kind === 'CLOZE' && opts && !Array.isArray(opts) && 'blanks' in opts) {
    return {
      ...q,
      options: {
        ...opts,
        blanks: opts.blanks.map((b) => ({
          ...b,
          choices: b.choices.length > 1 ? shuffle(b.choices) : b.choices,
        })),
      },
    };
  }
  if (kind === 'BOWTIE' && opts && !Array.isArray(opts) && 'categories' in opts) {
    return {
      ...q,
      options: {
        ...opts,
        categories: opts.categories.map((c) => ({
          ...c,
          choices: c.choices.length > 1 ? shuffle(c.choices) : c.choices,
        })),
      },
    };
  }
  return q;
}

/** Overlay a frozen per-question choice permutation onto the live bank/exam rows. */
export function applyOptionOrder<T extends { id: number; options?: QuestionOptions | null }>(
  questions: T[],
  optionOrder: Record<string, QuestionOptions> | null | undefined,
): T[] {
  if (!optionOrder) return questions;
  return questions.map((q) => {
    const stored = optionOrder[String(q.id)];
    return stored !== undefined ? { ...q, options: stored } : q;
  });
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

export interface KindCount {
  kind: string;
  count: number;
}

export interface ExamSummary {
  id: string;
  title: string;
  course_id: string | null;
  course_name: string | null;
  time_limit_minutes: number | null;
  /** The passing score as a percentage, 1-100. Chosen per exam at upload. */
  pass_grade: number;
  /** When false, attempts keep insertion order instead of shuffling. */
  shuffle: boolean;
  /** How many questions a student sits per attempt. Null = every question. */
  questions_per_attempt: number | null;
  /** Practice mode reveals the answer key, so a graded exam has this off. */
  allow_practice: boolean;
  /** Only the owner may rename, edit, delete or re-flag an exam. */
  is_owner: boolean;
  /** Peer instructor invited to manage this exam (not classroom `is_shared`). */
  is_collaborator?: boolean;
  total_questions: number;
  mcq_count: number;
  sata_count: number;
  fib_count: number;
  other_count?: number;
  /** Present kinds only — preferred over the collapsed mcq/sata/fib/other fields. */
  kind_counts: KindCount[];
  created_at: string;
  /** Set when this exam draws each attempt from a question bank. */
  bank_id?: string | null;
}

export interface SectionShare {
  section_id: string;
  name: string;
  percent: number;
  question_count: number;
}

export interface ExamDetail {
  id: string;
  title: string;
  course_name?: string | null;
  time_limit_minutes?: number | null;
  pass_grade: number;
  shuffle: boolean;
  questions_per_attempt: number | null;
  /**
   * Whether `answer`/`rationale` are present on the questions below. The server
   * withholds them unless you own the exam or practice is allowed, so never
   * infer it from a field being missing.
   */
  answers_included: boolean;
  allow_practice: boolean;
  is_owner: boolean;
  is_collaborator?: boolean;
  questions: Question[];
  bank_id?: string | null;
  bank_backed?: boolean;
  section_shares?: SectionShare[] | null;
}

export interface ExamCollaborator {
  user_id: string;
  email: string;
  created_at: string;
}

export interface QuestionBankSummary {
  id: string;
  title: string;
  course_id: string | null;
  course_name: string | null;
  section_count: number;
  question_count: number;
  created_at: string;
  is_owner?: boolean;
  is_collaborator?: boolean;
}

export interface BankSection {
  id: string;
  name: string;
  position: number;
  question_count: number;
  questions: Question[];
}

export interface QuestionBankDetail {
  id: string;
  title: string;
  course_id: string | null;
  course_name: string | null;
  created_at: string;
  sections: BankSection[];
}

export interface AnswerSubmission {
  question_id: number;
  answer: AnswerValue;
  fib_correct?: boolean | null;
}

export interface SubmissionPayload {
  exam_id: string;
  answers: AnswerSubmission[];
  time_spent_seconds: number;
  mode?: string;
  question_ids?: number[];
}

export interface QuestionResult {
  question_id: number;
  /** 1-based position in this attempt — display only, not identity. */
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
  /** Frozen display order of each question's choices for this attempt. */
  option_order?: Record<string, QuestionOptions>;
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
  option_order?: Record<string, QuestionOptions>;
  remaining_seconds: number;
  current_page: number;
}

// ── Platform administration ─────────────────────────────────────
//
// Everything below is served from `/api/platform`, which requires the admin
// role exactly — `/api/admin` is the instructor surface and accepts either staff
// role. The two prefixes are not interchangeable.

/** Shared page envelope for the admin listing endpoints. */
export interface Paged<T> {
  items: T[];
  /** Matches the current filter, not the table — tells the page if more exist. */
  total: number;
  limit: number;
  offset: number;
}

/** One account as the Users table lists it. Counts are aggregates, not columns. */
export interface AdminUser {
  id: string;
  email: string;
  role: UserRole;
  /** Null until onboarding sets it, which also flags a half-finished sign-up. */
  display_name: string | null;
  avatar: string | null;
  /** Staff only, and a credential: holding it enrols students under that account. */
  invite_code: string | null;
  instructor_id: string | null;
  instructor_name: string | null;
  /** Size of this account's own roster. Always 0 for a student. */
  student_count: number;
  attempts: number;
  in_progress_count: number;
  created_at: string;
}

export interface AdminUserRollup {
  attempts: number;
  exam_attempts: number;
  practice_attempts: number;
  average_score: number;
  best_score: number;
  pass_rate: number;
  total_seconds: number;
  last_attempt_at: string | null;
}

export interface AdminUserDetail {
  user: AdminUser;
  rollup: AdminUserRollup;
  owned_exams: number;
  owned_courses: number;
  /** Populated for staff only: the accounts enrolled with this one. */
  students: AdminUser[];
  recent_attempts: StudentAttempt[];
}

export interface AdminUserCreate {
  email: string;
  password: string;
  role: UserRole;
  display_name?: string | null;
  /** Required for a student, ignored for staff. */
  instructor_id?: string | null;
}

/** Partial update. Omit a field to leave it alone. */
export interface AdminUserUpdate {
  role?: UserRole;
  display_name?: string;
  instructor_id?: string | null;
}

/** A staff member with their class aggregates and enrolment code. */
export interface AdminInstructor {
  instructor_id: string;
  display_name: string | null;
  email: string;
  role: UserRole;
  invite_code: string | null;
  students: number;
  attempts: number;
  average_score: number;
  pass_rate: number;
  last_attempt_at: string | null;
}

export interface AdminExam {
  id: string;
  title: string;
  owner_id: string;
  owner_email: string | null;
  owner_name: string | null;
  course_name: string | null;
  is_shared: boolean;
  allow_practice: boolean;
  pass_grade: number;
  time_limit_minutes: number | null;
  total_questions: number;
  created_at: string;
}

export interface AdminCourse {
  id: string;
  name: string;
  owner_id: string;
  owner_email: string | null;
  owner_name: string | null;
  is_shared: boolean;
  created_at: string;
}

/** Partial update for an exam or a course. Omit a field to leave it alone. */
export interface AdminContentUpdate {
  is_shared?: boolean;
  owner_id?: string;
}

export interface AuditEntry {
  id: string;
  /** Null once the acting admin's account is deleted; the email survives. */
  actor_id: string | null;
  actor_email: string;
  action: string;
  target_type: string;
  target_id: string | null;
  target_label: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface PlatformOverview {
  user_count: number;
  student_count: number;
  instructor_count: number;
  admin_count: number;
  /** Registered but never named, so every sign-in returns them to onboarding. */
  pending_onboarding: number;
  course_count: number;
  exam_count: number;
  attempts: number;
  recent_attempts: number;
  live_now: number;
  average_score: number;
  pass_rate: number;
  total_seconds: number;
  attempts_per_day: DailyPoint[];
  /** Ten 10-point score bands, low to high. Always exactly ten entries. */
  score_buckets: number[];
  passed_count: number;
  failed_count: number;
  instructor_rollups: AdminInstructor[];
  topic_stats: TopicStat[];
}

export interface SystemCounts {
  users: number;
  courses: number;
  exams: number;
  questions: number;
  attempts: number;
  in_progress: number;
  audit_entries: number;
}

export interface StorageStat {
  files: number;
  bytes: number;
}

/** `available` is false when ./backups is not mounted into the API container. */
export interface BackupInfo {
  available: boolean;
  files: number;
  bytes: number;
  latest_name: string | null;
  latest_bytes: number | null;
  latest_at: string | null;
}

export interface SystemInfo {
  environment: string;
  api_docs_enabled: boolean;
  log_level: string;
  postgres_version: string;
  database_bytes: number;
  counts: SystemCounts;
  uploads: StorageStat;
  documents: StorageStat;
  backups: BackupInfo;
}

/** Human-readable byte size: "4.2 MB", "812 kB", "0 B". */
export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B';
  const units = ['B', 'kB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  // Whole bytes never need a decimal; everything else reads better with one.
  return `${exponent === 0 ? value : value.toFixed(1)} ${units[exponent]}`;
}

/** "user.role_changed" -> "Role changed". Keeps the log readable without a map. */
export function formatAuditAction(action: string): string {
  const verb = action.split('.').slice(1).join('.') || action;
  const words = verb.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Title-cased role, for badges and pickers. */
export function formatRole(role: UserRole): string {
  return role.charAt(0).toUpperCase() + role.slice(1);
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
    options?: {
      shuffle?: boolean;
      questionsPerAttempt?: number | null;
    },
  ): Observable<{ exam_id: string; total_questions: number }> {
    const body: Record<string, unknown> = {
      title,
      questions,
      pass_grade: passGrade,
      shuffle: options?.shuffle ?? true,
    };
    if (courseId) body['course_id'] = courseId;
    if (timeLimitMinutes) body['time_limit_minutes'] = timeLimitMinutes;
    if (options?.questionsPerAttempt != null) {
      body['questions_per_attempt'] = options.questionsPerAttempt;
    }
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

  getExam(id: string, includeAnswers = false, mode?: string): Observable<ExamDetail> {
    let params = new HttpParams();
    if (includeAnswers) params = params.set('include_answers', 'true');
    if (mode) params = params.set('mode', mode);
    return this.http.get<ExamDetail>(`${this.base}/exams/${id}`, { params });
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

  updateExamSettings(
    id: string,
    settings: {
      timeLimitMinutes?: number | null;
      shuffle?: boolean;
      questionsPerAttempt?: number | null;
      clearQuestionsPerAttempt?: boolean;
      shares?: { section_id: string; percent: number }[];
    },
  ): Observable<ExamSummary> {
    const body: Record<string, unknown> = {};
    if ('timeLimitMinutes' in settings)
      body['time_limit_minutes'] = settings.timeLimitMinutes ?? null;
    if (settings.shuffle !== undefined) body['shuffle'] = settings.shuffle;
    if (settings.clearQuestionsPerAttempt) body['clear_questions_per_attempt'] = true;
    else if (settings.questionsPerAttempt != null) {
      body['questions_per_attempt'] = settings.questionsPerAttempt;
    }
    if (settings.shares) body['shares'] = settings.shares;
    return this.http.patch<ExamSummary>(`${this.base}/exams/${id}/settings`, body);
  }

  listExamCollaborators(examId: string): Observable<ExamCollaborator[]> {
    return this.http.get<ExamCollaborator[]>(`${this.base}/exams/${examId}/collaborators`);
  }

  addExamCollaborator(examId: string, email: string): Observable<ExamCollaborator> {
    return this.http.post<ExamCollaborator>(`${this.base}/exams/${examId}/collaborators`, {
      email,
    });
  }

  removeExamCollaborator(examId: string, userId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${this.base}/exams/${examId}/collaborators/${userId}`,
    );
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

  /**
   * Clear somebody else's open attempt. Students cannot discard a graded attempt
   * of their own, so without this an abandoned one locks them out of that exam.
   *
   * Two routes do the same thing and the caller's role decides which: the
   * platform one writes an audit entry, the instructor one does not. Prefer the
   * audited path whenever the caller can use it — see `resetLiveAttempt` on the
   * Tracking page, which is the only caller of either.
   */
  resetStudentAttempt(recordId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/admin/in-progress/${recordId}`);
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

  // ── Platform administration ──────────────────────────────────
  //
  // Admin-only, and deployment-wide rather than scoped to one instructor's
  // students. Note the prefix: `/api/platform`, not `/api/admin`.

  getPlatformOverview(): Observable<PlatformOverview> {
    return this.http.get<PlatformOverview>(`${this.base}/platform/overview`);
  }

  listAdminUsers(
    query: string,
    role: UserRole | '',
    limit: number,
    offset: number,
  ): Observable<Paged<AdminUser>> {
    let params = new HttpParams().set('limit', limit).set('offset', offset);
    if (query) params = params.set('q', query);
    if (role) params = params.set('role', role);
    return this.http.get<Paged<AdminUser>>(`${this.base}/platform/users`, { params });
  }

  getAdminUser(userId: string): Observable<AdminUserDetail> {
    return this.http.get<AdminUserDetail>(`${this.base}/platform/users/${userId}`);
  }

  createAdminUser(payload: AdminUserCreate): Observable<AdminUser> {
    return this.http.post<AdminUser>(`${this.base}/platform/users`, payload);
  }

  updateAdminUser(userId: string, patch: AdminUserUpdate): Observable<AdminUser> {
    return this.http.patch<AdminUser>(`${this.base}/platform/users/${userId}`, patch);
  }

  resetUserPassword(userId: string, newPassword: string): Observable<{ revoked: boolean }> {
    return this.http.post<{ revoked: boolean }>(`${this.base}/platform/users/${userId}/password`, {
      new_password: newPassword,
    });
  }

  revokeUserSessions(userId: string): Observable<{ revoked: boolean }> {
    return this.http.post<{ revoked: boolean }>(
      `${this.base}/platform/users/${userId}/revoke-sessions`,
      {},
    );
  }

  impersonateUser(userId: string): Observable<{ token: string; user: AuthUser }> {
    return this.http.post<{ token: string; user: AuthUser }>(
      `${this.base}/platform/users/${userId}/impersonate`,
      {},
    );
  }

  endImpersonation(): Observable<{ token: string; user: AuthUser }> {
    return this.http.post<{ token: string; user: AuthUser }>(
      `${this.base}/platform/impersonate/end`,
      {},
    );
  }

  deleteAdminUser(userId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/platform/users/${userId}`);
  }

  listAdminInstructors(): Observable<AdminInstructor[]> {
    return this.http.get<AdminInstructor[]>(`${this.base}/platform/instructors`);
  }

  rotateInviteCode(userId: string): Observable<{ invite_code: string }> {
    return this.http.post<{ invite_code: string }>(
      `${this.base}/platform/instructors/${userId}/rotate-code`,
      {},
    );
  }

  reassignStudents(fromId: string, toInstructorId: string): Observable<{ moved: number }> {
    return this.http.post<{ moved: number }>(
      `${this.base}/platform/instructors/${fromId}/reassign-students`,
      { to_instructor_id: toInstructorId },
    );
  }

  listAdminExams(
    query: string,
    shared: boolean | null,
    limit: number,
    offset: number,
  ): Observable<Paged<AdminExam>> {
    let params = new HttpParams().set('limit', limit).set('offset', offset);
    if (query) params = params.set('q', query);
    if (shared !== null) params = params.set('shared', shared);
    return this.http.get<Paged<AdminExam>>(`${this.base}/platform/exams`, { params });
  }

  updateAdminExam(examId: string, patch: AdminContentUpdate): Observable<{ updated: boolean }> {
    return this.http.patch<{ updated: boolean }>(`${this.base}/platform/exams/${examId}`, patch);
  }

  deleteAdminExam(examId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/platform/exams/${examId}`);
  }

  listAdminCourses(query: string, limit: number, offset: number): Observable<Paged<AdminCourse>> {
    let params = new HttpParams().set('limit', limit).set('offset', offset);
    if (query) params = params.set('q', query);
    return this.http.get<Paged<AdminCourse>>(`${this.base}/platform/courses`, { params });
  }

  updateAdminCourse(courseId: string, patch: AdminContentUpdate): Observable<{ updated: boolean }> {
    return this.http.patch<{ updated: boolean }>(
      `${this.base}/platform/courses/${courseId}`,
      patch,
    );
  }

  deleteAdminCourse(courseId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/platform/courses/${courseId}`);
  }

  /** The audited twin of `resetStudentAttempt`. */
  resetPlatformAttempt(recordId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/platform/in-progress/${recordId}`);
  }

  listAudit(action: string, limit: number, offset: number): Observable<Paged<AuditEntry>> {
    let params = new HttpParams().set('limit', limit).set('offset', offset);
    // Prefix match server-side, so "user." selects every account action.
    if (action) params = params.set('action', action);
    return this.http.get<Paged<AuditEntry>>(`${this.base}/platform/audit`, { params });
  }

  getSystemInfo(): Observable<SystemInfo> {
    return this.http.get<SystemInfo>(`${this.base}/platform/system`);
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

  // ── Question banks (instructor) ──────────────────────────────

  listBanks(): Observable<QuestionBankSummary[]> {
    return this.http.get<QuestionBankSummary[]>(`${this.base}/question-banks`);
  }

  createBank(title: string, courseId?: string): Observable<QuestionBankSummary> {
    const body: Record<string, unknown> = { title };
    if (courseId) body['course_id'] = courseId;
    return this.http.post<QuestionBankSummary>(`${this.base}/question-banks`, body);
  }

  getBank(id: string): Observable<QuestionBankDetail> {
    return this.http.get<QuestionBankDetail>(`${this.base}/question-banks/${id}`);
  }

  updateBank(
    id: string,
    patch: { title?: string; course_id?: string | null },
  ): Observable<QuestionBankSummary> {
    return this.http.patch<QuestionBankSummary>(`${this.base}/question-banks/${id}`, patch);
  }

  deleteBank(id: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/question-banks/${id}`);
  }

  addBankSection(bankId: string, name: string): Observable<BankSection> {
    return this.http.post<BankSection>(`${this.base}/question-banks/${bankId}/sections`, { name });
  }

  renameBankSection(bankId: string, sectionId: string, name: string): Observable<BankSection> {
    return this.http.patch<BankSection>(
      `${this.base}/question-banks/${bankId}/sections/${sectionId}`,
      { name },
    );
  }

  deleteBankSection(bankId: string, sectionId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${this.base}/question-banks/${bankId}/sections/${sectionId}`,
    );
  }

  addBankQuestions(
    bankId: string,
    sectionId: string,
    questions: Partial<Question>[],
  ): Observable<{ added: number }> {
    return this.http.post<{ added: number }>(
      `${this.base}/question-banks/${bankId}/sections/${sectionId}/questions`,
      { questions },
    );
  }

  updateBankQuestion(
    bankId: string,
    sectionId: string,
    questionId: number,
    patch: Partial<Question>,
  ): Observable<Question> {
    return this.http.patch<Question>(
      `${this.base}/question-banks/${bankId}/sections/${sectionId}/questions/${questionId}`,
      patch,
    );
  }

  deleteBankQuestion(
    bankId: string,
    sectionId: string,
    questionId: number,
  ): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${this.base}/question-banks/${bankId}/sections/${sectionId}/questions/${questionId}`,
    );
  }

  createExamFromBank(payload: {
    title: string;
    bank_id: string;
    shares: { section_id: string; percent: number }[];
    questions_per_attempt: number;
    course_id?: string;
    time_limit_minutes?: number | null;
    pass_grade: number;
    shuffle: boolean;
  }): Observable<{ exam_id: string; total_questions: number }> {
    return this.http.post<{ exam_id: string; total_questions: number }>(
      `${this.base}/exams/from-bank`,
      payload,
    );
  }
}
