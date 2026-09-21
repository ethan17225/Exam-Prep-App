import {
  Question,
  QuestionKind,
  QuestionSection,
  SectionBlock,
  TableBlock,
  HotspotRegion,
  classifyQuestionType,
  kindFromType,
  matrixRows,
  matrixColumns,
  clozeBlanks,
  bowtieCategories,
  highlightTokens,
  hotspotRegions,
  rankingItems,
} from '../../services/exam.service';

export const QUESTION_TYPES = [
  'MCQ',
  'SATA',
  'FIB',
  'MATRIX',
  'CLOZE',
  'BOWTIE',
  'RANKING',
  'HIGHLIGHT',
  'HOTSPOT',
];

export interface ClozeBlankDraft {
  label: string;
  choicesText: string;
  answer: string;
}

export interface BowtieCategoryDraft {
  name: string;
  count: number;
  choicesText: string;
  answer: string[];
}

export interface HighlightTokenDraft {
  text: string;
  correct: boolean;
}

export type BlockKind = 'text' | 'list' | 'table';

export interface SectionBlockDraft {
  kind: BlockKind;
  text: string;
  itemsText: string;
  caption: string;
  headers: string[];
  rows: string[][];
  pasteOpen: boolean;
  pasteText: string;
}

export interface SectionDraft {
  title: string;
  blocks: SectionBlockDraft[];
  collapsed: boolean;
}

export interface QuestionDraft {
  id: number;
  topic: string;
  type: string;
  question: string;
  rationale: string;
  image: string | null;
  sections: SectionDraft[];
  optionsText: string;
  answerText: string;
  matrixRowsText: string;
  matrixColsText: string;
  matrixAnswer: Record<string, string[]>;
  clozeBlanks: ClozeBlankDraft[];
  bowtieCategories: BowtieCategoryDraft[];
  rankingText: string;
  highlightTokens: HighlightTokenDraft[];
  regions: HotspotRegion[];
  hotspotAnswer: string;
}

export function emptyDraft(id: number, type = 'MCQ'): QuestionDraft {
  return {
    id,
    topic: '',
    type,
    question: '',
    rationale: '',
    image: null,
    sections: [],
    optionsText: '',
    answerText: '',
    matrixRowsText: '',
    matrixColsText: '',
    matrixAnswer: {},
    clozeBlanks: [],
    bowtieCategories: [],
    rankingText: '',
    highlightTokens: [],
    regions: [],
    hotspotAnswer: '',
  };
}

export function lines(text: string): string[] {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
}

export function kindOf(d: QuestionDraft): QuestionKind {
  return kindFromType(d.type);
}

export function preview(d: QuestionDraft): string {
  const text = (d.question || '').replace(/\s+/g, ' ').trim();
  return text.length > 140 ? text.slice(0, 140) + '…' : text;
}

function toBlockDraft(block: SectionBlock): SectionBlockDraft {
  const draft: SectionBlockDraft = {
    kind: 'text',
    text: '',
    itemsText: '',
    caption: '',
    headers: [],
    rows: [],
    pasteOpen: false,
    pasteText: '',
  };
  if (block?.type === 'list') {
    draft.kind = 'list';
    draft.itemsText = (block.items ?? []).join('\n');
  } else if (block?.type === 'table') {
    const t = block as TableBlock;
    draft.kind = 'table';
    draft.caption = t.caption ?? '';
    draft.headers = [...(t.headers ?? [])];
    draft.rows = (t.rows ?? []).map((r) => [...r]);
  } else {
    draft.kind = 'text';
    draft.text = (block as { text?: string })?.text ?? '';
  }
  return draft;
}

export function toSectionDrafts(sections: QuestionSection[] | null | undefined): SectionDraft[] {
  if (!Array.isArray(sections)) return [];
  return sections.map((s) => ({
    title: s.title ?? '',
    collapsed: true,
    blocks: (Array.isArray(s.blocks) ? s.blocks : []).map((b) => toBlockDraft(b)),
  }));
}

export function toDraft(q: Question): QuestionDraft {
  const kind = classifyQuestionType(q);
  const draft: QuestionDraft = {
    ...emptyDraft(
      q.id,
      (q.type || 'MCQ').toUpperCase() === 'FILL-IN-THE-BLANK' ? 'FIB' : q.type || 'MCQ',
    ),
    topic: q.topic ?? '',
    question: q.question ?? '',
    rationale: q.rationale ?? '',
    image: q.image ?? null,
    sections: toSectionDrafts(q.sections),
  };

  if (kind === 'MCQ' || kind === 'SATA') {
    draft.optionsText = (Array.isArray(q.options) ? q.options : []).join('\n');
    draft.answerText = Array.isArray(q.answer)
      ? (q.answer as string[]).join(', ')
      : String(q.answer ?? '');
  } else if (kind === 'FIB') {
    draft.answerText = String(q.answer ?? '');
  } else if (kind === 'MATRIX') {
    draft.matrixRowsText = matrixRows(q).join('\n');
    draft.matrixColsText = matrixColumns(q).join('\n');
    const ans = q.answer;
    if (ans && typeof ans === 'object' && !Array.isArray(ans)) {
      draft.matrixAnswer = Object.fromEntries(
        Object.entries(ans as Record<string, string[]>).map(([k, v]) => [
          String(k),
          [...(v ?? [])],
        ]),
      );
    }
  } else if (kind === 'CLOZE') {
    const answers = Array.isArray(q.answer) ? (q.answer as string[]) : [];
    draft.clozeBlanks = clozeBlanks(q).map((b, i) => ({
      label: b.label ?? `Blank ${i + 1}`,
      choicesText: (b.choices ?? []).join('\n'),
      answer: String(answers[i] ?? ''),
    }));
  } else if (kind === 'BOWTIE') {
    const ans =
      q.answer && typeof q.answer === 'object' && !Array.isArray(q.answer)
        ? (q.answer as Record<string, string[]>)
        : {};
    draft.bowtieCategories = bowtieCategories(q).map((c) => ({
      name: c.name,
      count: c.count || 1,
      choicesText: (c.choices ?? []).join('\n'),
      answer: [...(ans[c.name] ?? [])],
    }));
  } else if (kind === 'RANKING') {
    const correct = Array.isArray(q.answer) ? (q.answer as string[]) : rankingItems(q);
    draft.rankingText = correct.map(String).join('\n');
  } else if (kind === 'HIGHLIGHT') {
    const correct = new Set(Array.isArray(q.answer) ? (q.answer as number[]).map(Number) : []);
    draft.highlightTokens = highlightTokens(q).map((t, i) => ({
      text: t,
      correct: correct.has(i),
    }));
  } else if (kind === 'HOTSPOT') {
    draft.regions = hotspotRegions(q).map((r) => ({ ...r }));
    draft.hotspotAnswer = String(q.answer ?? '');
  }

  return draft;
}

export function serializeSections(d: QuestionDraft): QuestionSection[] | null {
  const out: QuestionSection[] = [];
  for (const s of d.sections) {
    const blocks: SectionBlock[] = [];
    for (const b of s.blocks) {
      if (b.kind === 'text') {
        const text = b.text.trim();
        if (text) blocks.push({ type: 'text', text });
      } else if (b.kind === 'list') {
        const items = lines(b.itemsText);
        if (items.length) blocks.push({ type: 'list', items });
      } else {
        const headers = b.headers.map((h) => h.trim());
        const rows = b.rows
          .map((r) => r.map((c) => (c ?? '').trim()))
          .filter((r) => r.some((c) => c !== ''));
        if (headers.some((h) => h !== '') || rows.length) {
          const table: TableBlock = { type: 'table', headers, rows };
          if (b.caption.trim()) table.caption = b.caption.trim();
          blocks.push(table);
        }
      }
    }
    if (blocks.length) out.push({ title: s.title.trim() || 'Patient Data', blocks });
  }
  return out.length ? out : null;
}

export function serialize(
  d: QuestionDraft,
): { options: unknown; answer: unknown } | { error: string } {
  const kind = kindOf(d);

  if (kind === 'MCQ') {
    const options = lines(d.optionsText);
    if (options.length < 2) return { error: 'MCQ needs at least 2 options (one per line).' };
    const answer = d.answerText.trim();
    if (!answer) return { error: 'Enter the correct answer letter (e.g. C).' };
    return { options, answer };
  }
  if (kind === 'SATA') {
    const options = lines(d.optionsText);
    if (options.length < 2) return { error: 'SATA needs at least 2 options (one per line).' };
    const answer = d.answerText
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (!answer.length) return { error: 'Enter the correct answer letters (e.g. A, B, D).' };
    return { options, answer };
  }
  if (kind === 'FIB') {
    const answer = d.answerText.trim();
    if (!answer) return { error: 'Enter the expected answer.' };
    return { options: null, answer };
  }
  if (kind === 'MATRIX') {
    const rows = lines(d.matrixRowsText);
    const columns = lines(d.matrixColsText);
    if (!rows.length || !columns.length)
      return { error: 'MATRIX needs at least one row and one column.' };
    const answer: Record<string, string[]> = {};
    for (let i = 0; i < rows.length; i++) {
      const sel = (d.matrixAnswer[String(i)] ?? []).filter((c) => columns.includes(c));
      if (sel.length) answer[String(i)] = sel;
    }
    if (!Object.keys(answer).length)
      return { error: 'Mark at least one correct cell in the answer grid.' };
    return { options: { rows, columns }, answer };
  }
  if (kind === 'CLOZE') {
    if (!d.clozeBlanks.length) return { error: 'CLOZE needs at least one blank.' };
    const blanks = [];
    const answer: string[] = [];
    for (const b of d.clozeBlanks) {
      const choices = lines(b.choicesText);
      if (choices.length < 2) return { error: `Blank "${b.label}" needs at least 2 choices.` };
      if (!b.answer || !choices.includes(b.answer)) {
        return { error: `Pick a correct choice for blank "${b.label}".` };
      }
      blanks.push({ label: b.label.trim() || 'Blank', choices });
      answer.push(b.answer);
    }
    return { options: { blanks }, answer };
  }
  if (kind === 'BOWTIE') {
    if (!d.bowtieCategories.length) return { error: 'BOWTIE needs at least one category.' };
    const categories = [];
    const answer: Record<string, string[]> = {};
    for (const c of d.bowtieCategories) {
      const choices = lines(c.choicesText);
      const name = c.name.trim();
      if (!name) return { error: 'Every BOWTIE category needs a name.' };
      if (choices.length < 2) return { error: `Category "${name}" needs at least 2 choices.` };
      const selected = c.answer.filter((a) => choices.includes(a));
      if (!selected.length)
        return { error: `Select the correct choice(s) for category "${name}".` };
      categories.push({ name, count: Math.max(1, Number(c.count) || selected.length), choices });
      answer[name] = selected;
    }
    return { options: { categories }, answer };
  }
  if (kind === 'RANKING') {
    const items = lines(d.rankingText);
    if (items.length < 2)
      return { error: 'RANKING needs at least 2 items (one per line, in correct order).' };
    const options = [...items.slice(1), items[0]];
    return { options, answer: items };
  }
  if (kind === 'HIGHLIGHT') {
    const tokens = d.highlightTokens.map((t) => t.text.trim()).filter(Boolean);
    if (tokens.length < 2) return { error: 'HIGHLIGHT needs at least 2 phrases.' };
    const answer: number[] = [];
    let idx = 0;
    for (const t of d.highlightTokens) {
      if (!t.text.trim()) continue;
      if (t.correct) answer.push(idx);
      idx++;
    }
    if (!answer.length) return { error: 'Mark at least one phrase as correct.' };
    return { options: { tokens }, answer };
  }
  if (kind === 'HOTSPOT') {
    if (!d.regions.length)
      return { error: 'HOTSPOT needs at least one region (draw on the image or add manually).' };
    if (!d.hotspotAnswer || !d.regions.some((r) => r.id === d.hotspotAnswer)) {
      return { error: 'Select which region is the correct answer.' };
    }
    const regions = d.regions.map((r) => ({
      ...r,
      label: r.label.trim() || r.id,
      x: Math.round(r.x * 100) / 100,
      y: Math.round(r.y * 100) / 100,
      w: Math.round(r.w * 100) / 100,
      h: Math.round(r.h * 100) / 100,
    }));
    return { options: { regions }, answer: d.hotspotAnswer };
  }
  return { error: `Unknown question type "${d.type}".` };
}

export function typeChangePatch(d: QuestionDraft, type: string): Partial<QuestionDraft> {
  const patch: Partial<QuestionDraft> = { type };
  const kind = kindFromType(type);
  if (kind === 'CLOZE' && d.clozeBlanks.length === 0) {
    patch.clozeBlanks = [{ label: 'Blank 1', choicesText: '', answer: '' }];
  }
  if (kind === 'BOWTIE' && d.bowtieCategories.length === 0) {
    patch.bowtieCategories = [{ name: 'Category 1', count: 1, choicesText: '', answer: [] }];
  }
  if (kind === 'HIGHLIGHT' && d.highlightTokens.length === 0) {
    patch.highlightTokens = [
      { text: '', correct: false },
      { text: '', correct: false },
    ];
  }
  return patch;
}

export function newBlockDraft(kind: BlockKind): SectionBlockDraft {
  const block: SectionBlockDraft = {
    kind,
    text: '',
    itemsText: '',
    caption: '',
    headers: [],
    rows: [],
    pasteOpen: false,
    pasteText: '',
  };
  if (kind === 'table') {
    block.headers = ['Column 1', 'Column 2'];
    block.rows = [['', '']];
  }
  return block;
}

export const DEFAULT_MCQ_PAYLOAD = {
  topic: '',
  type: 'MCQ',
  question: 'New question',
  options: ['A. Option 1', 'B. Option 2', 'C. Option 3', 'D. Option 4'],
  answer: 'A',
  rationale: '',
};

/** Ties-to-even, same as the backend's `round()`. */
function pythonRound(n: number): number {
  const floor = Math.floor(n);
  const frac = n - floor;
  if (frac > 0.5) return floor + 1;
  if (frac < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** How many questions `percent` of `size` draws, matching Python 3 `round()`. */
export function expectedDraw(size: number, percent: number): number {
  if (size <= 0 || percent <= 0) return 0;
  return Math.min(size, Math.max(0, pythonRound((size * percent) / 100)));
}

/**
 * How many questions to take from each section for an exam of `total` questions.
 * Percents are weights of that total (largest remainder, then spill into sections
 * that still have room). `total === null` is the legacy percent-of-section mix.
 */
export function allocateSectionDraws(
  total: number | null,
  sizes: number[],
  percents: number[],
): number[] {
  const n = sizes.length;
  if (n === 0) return [];
  if (total == null) {
    return sizes.map((size, i) => expectedDraw(size, percents[i] ?? 0));
  }

  const pool = sizes.reduce((sum, size) => sum + Math.max(0, size), 0);
  const target = Math.min(Math.max(0, total), pool);
  if (target === 0) return sizes.map(() => 0);

  const weightSum = percents.reduce((sum, p) => sum + Math.max(0, p), 0);
  if (weightSum <= 0) return sizes.map(() => 0);

  const quotas = percents.map((p) => (target * Math.max(0, p)) / weightSum);
  const draws = quotas.map((q, i) => Math.min(sizes[i] ?? 0, Math.floor(q)));
  let leftover = target - draws.reduce((sum, d) => sum + d, 0);

  const remainderOrder = [...Array(n).keys()].sort((a, b) => {
    const d = quotas[b]! - Math.floor(quotas[b]!) - (quotas[a]! - Math.floor(quotas[a]!));
    if (d !== 0) return d;
    return a - b;
  });
  for (const i of remainderOrder) {
    if (leftover <= 0) break;
    if (draws[i]! < (sizes[i] ?? 0)) {
      draws[i]! += 1;
      leftover -= 1;
    }
  }

  const roomOrder = [...Array(n).keys()].sort(
    (a, b) => (sizes[b] ?? 0) - draws[b]! - ((sizes[a] ?? 0) - draws[a]!) || a - b,
  );
  while (leftover > 0) {
    let progressed = false;
    for (const i of roomOrder) {
      if (leftover <= 0) break;
      if (draws[i]! < (sizes[i] ?? 0)) {
        draws[i]! += 1;
        leftover -= 1;
        progressed = true;
      }
    }
    if (!progressed) break;
  }
  return draws;
}
