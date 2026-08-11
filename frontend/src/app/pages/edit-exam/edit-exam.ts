import { Component, OnDestroy, OnInit, signal, WritableSignal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  ExamService,
  Question,
  QuestionKind,
  HotspotRegion,
  QuestionSection,
  SectionBlock,
  TableBlock,
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

interface ClozeBlankDraft {
  label: string;
  choicesText: string;
  answer: string;
}

interface BowtieCategoryDraft {
  name: string;
  count: number;
  choicesText: string;
  answer: string[];
}

interface HighlightTokenDraft {
  text: string;
  correct: boolean;
}

type BlockKind = 'text' | 'list' | 'table';

interface SectionBlockDraft {
  kind: BlockKind;
  text: string;
  itemsText: string;
  caption: string;
  headers: string[];
  rows: string[][];
  pasteOpen: boolean;
  pasteText: string;
}

interface SectionDraft {
  title: string;
  blocks: SectionBlockDraft[];
  collapsed: boolean;
}

interface QuestionDraft {
  id: number;
  number: number;
  topic: string;
  type: string;
  question: string;
  rationale: string;
  image: string | null;
  // Tabbed patient data
  sections: SectionDraft[];
  // MCQ / SATA / FIB
  optionsText: string;
  answerText: string;
  // MATRIX
  matrixRowsText: string;
  matrixColsText: string;
  matrixAnswer: Record<string, string[]>;
  // CLOZE
  clozeBlanks: ClozeBlankDraft[];
  // BOWTIE
  bowtieCategories: BowtieCategoryDraft[];
  // RANKING (items in correct order, one per line)
  rankingText: string;
  // HIGHLIGHT
  highlightTokens: HighlightTokenDraft[];
  // HOTSPOT
  regions: HotspotRegion[];
  hotspotAnswer: string;
}

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

@Component({
  selector: 'app-edit-exam',
  imports: [FormsModule],
  templateUrl: './edit-exam.html',
  styleUrl: './edit-exam.scss',
})
export class EditExamPage implements OnInit, OnDestroy {
  examTitle = signal('');
  drafts = signal<QuestionDraft[]>([]);
  loading = signal(true);
  loadError = signal('');
  addingQuestion = signal(false);

  // Per-draft UI state, keyed by question id (never stored on the draft objects —
  // drafts are replaced copy-on-write and would lose it).
  expanded = signal<Record<number, boolean>>({});
  saving = signal<Record<number, boolean>>({});
  saved = signal<Record<number, boolean>>({});
  uploading = signal<Record<number, boolean>>({});
  draftError = signal<Record<number, string>>({});

  readonly questionTypes = QUESTION_TYPES;

  private examId = '';
  private savedTimers = new Map<number, ReturnType<typeof setTimeout>>();
  // Ids, not object references — draft objects are replaced on every edit.
  private drawing: { draftId: number; regionId: string; startX: number; startY: number } | null =
    null;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private examService: ExamService,
  ) {}

  ngOnInit(): void {
    this.examId = this.route.snapshot.paramMap.get('id')!;
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.getExam(this.examId, true).subscribe({
      next: (exam) => {
        // Every write here already 404s for a non-owner, but the read did not —
        // so opening the editor on someone else's exam used to display its key.
        if (!exam.is_owner) {
          this.loading.set(false);
          this.loadError.set('You can only edit exams you created.');
          return;
        }
        this.examTitle.set(exam.title);
        this.drafts.set(exam.questions.map((q) => this.toDraft(q)));
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Could not load this exam.');
      },
    });
  }

  ngOnDestroy(): void {
    for (const t of this.savedTimers.values()) clearTimeout(t);
    this.savedTimers.clear();
  }

  goBack(): void {
    this.router.navigate(['/exams']);
  }

  kindOf(d: QuestionDraft): QuestionKind {
    return kindFromType(d.type);
  }

  preview(d: QuestionDraft): string {
    const text = (d.question || '').replace(/\s+/g, ' ').trim();
    return text.length > 140 ? text.slice(0, 140) + '…' : text;
  }

  toggleExpand(d: QuestionDraft): void {
    this.expanded.set({ ...this.expanded(), [d.id]: !this.expanded()[d.id] });
  }

  // ── Copy-on-write draft updates ─────────────────────────────

  private updateDraft(id: number, patch: Partial<QuestionDraft>): void {
    this.drafts.update((list) => list.map((d) => (d.id === id ? { ...d, ...patch } : d)));
  }

  setDraftField<K extends keyof QuestionDraft>(
    d: QuestionDraft,
    key: K,
    value: QuestionDraft[K],
  ): void {
    this.updateDraft(d.id, { [key]: value } as Partial<QuestionDraft>);
  }

  private setFlag(sig: WritableSignal<Record<number, boolean>>, id: number, value: boolean): void {
    sig.set({ ...sig(), [id]: value });
  }

  private setError(id: number, message: string): void {
    this.draftError.set({ ...this.draftError(), [id]: message });
  }

  // ── Draft <-> Question mapping ──────────────────────────────

  private toDraft(q: Question): QuestionDraft {
    const kind = classifyQuestionType(q);
    const draft: QuestionDraft = {
      id: q.id!,
      number: q.number,
      topic: q.topic ?? '',
      type: (q.type || 'MCQ').toUpperCase() === 'FILL-IN-THE-BLANK' ? 'FIB' : q.type || 'MCQ',
      question: q.question ?? '',
      rationale: q.rationale ?? '',
      image: q.image ?? null,
      sections: this.toSectionDrafts(q.sections),
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

  private lines(text: string): string[] {
    return text
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
  }

  // ── Sections (tabbed patient data) ──────────────────────────

  private toSectionDrafts(sections: QuestionSection[] | null | undefined): SectionDraft[] {
    if (!Array.isArray(sections)) return [];
    return sections.map((s) => ({
      title: s.title ?? '',
      collapsed: true,
      blocks: (Array.isArray(s.blocks) ? s.blocks : []).map((b) => this.toBlockDraft(b)),
    }));
  }

  private toBlockDraft(block: SectionBlock): SectionBlockDraft {
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

  private serializeSections(d: QuestionDraft): QuestionSection[] | null {
    const out: QuestionSection[] = [];
    for (const s of d.sections) {
      const blocks: SectionBlock[] = [];
      for (const b of s.blocks) {
        if (b.kind === 'text') {
          const text = b.text.trim();
          if (text) blocks.push({ type: 'text', text });
        } else if (b.kind === 'list') {
          const items = this.lines(b.itemsText);
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

  private updateSection(d: QuestionDraft, si: number, patch: Partial<SectionDraft>): void {
    this.updateDraft(d.id, {
      sections: d.sections.map((s, i) => (i === si ? { ...s, ...patch } : s)),
    });
  }

  setSectionTitle(d: QuestionDraft, si: number, title: string): void {
    this.updateSection(d, si, { title });
  }

  addSection(d: QuestionDraft): void {
    this.updateDraft(d.id, {
      sections: [
        ...d.sections,
        {
          title: `Tab ${d.sections.length + 1}`,
          collapsed: false,
          blocks: [this.newBlockDraft('text')],
        },
      ],
    });
  }

  removeSection(d: QuestionDraft, si: number): void {
    this.updateDraft(d.id, { sections: d.sections.filter((_, i) => i !== si) });
  }

  moveSection(d: QuestionDraft, si: number, delta: number): void {
    const target = si + delta;
    if (target < 0 || target >= d.sections.length) return;
    const sections = [...d.sections];
    [sections[si], sections[target]] = [sections[target], sections[si]];
    this.updateDraft(d.id, { sections });
  }

  toggleSection(d: QuestionDraft, si: number): void {
    this.updateSection(d, si, { collapsed: !d.sections[si].collapsed });
  }

  private newBlockDraft(kind: BlockKind): SectionBlockDraft {
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

  private updateBlock(
    d: QuestionDraft,
    si: number,
    bi: number,
    patch: Partial<SectionBlockDraft>,
  ): void {
    this.updateSection(d, si, {
      blocks: d.sections[si].blocks.map((b, i) => (i === bi ? { ...b, ...patch } : b)),
    });
  }

  setBlockField<K extends keyof SectionBlockDraft>(
    d: QuestionDraft,
    si: number,
    bi: number,
    key: K,
    value: SectionBlockDraft[K],
  ): void {
    this.updateBlock(d, si, bi, { [key]: value } as Partial<SectionBlockDraft>);
  }

  addBlock(d: QuestionDraft, si: number, kind: BlockKind): void {
    this.updateSection(d, si, { blocks: [...d.sections[si].blocks, this.newBlockDraft(kind)] });
  }

  removeBlock(d: QuestionDraft, si: number, bi: number): void {
    this.updateSection(d, si, { blocks: d.sections[si].blocks.filter((_, i) => i !== bi) });
  }

  moveBlock(d: QuestionDraft, si: number, bi: number, delta: number): void {
    const blocks = [...d.sections[si].blocks];
    const target = bi + delta;
    if (target < 0 || target >= blocks.length) return;
    [blocks[bi], blocks[target]] = [blocks[target], blocks[bi]];
    this.updateSection(d, si, { blocks });
  }

  // ── Table block editing ─────────────────────────────────────

  setHeader(d: QuestionDraft, si: number, bi: number, hi: number, value: string): void {
    const block = d.sections[si].blocks[bi];
    this.updateBlock(d, si, bi, { headers: block.headers.map((h, i) => (i === hi ? value : h)) });
  }

  setCell(d: QuestionDraft, si: number, bi: number, ri: number, ci: number, value: string): void {
    const block = d.sections[si].blocks[bi];
    this.updateBlock(d, si, bi, {
      rows: block.rows.map((row, r) =>
        r === ri ? row.map((c, i) => (i === ci ? value : c)) : row,
      ),
    });
  }

  addTableRow(d: QuestionDraft, si: number, bi: number): void {
    const block = d.sections[si].blocks[bi];
    this.updateBlock(d, si, bi, {
      rows: [...block.rows, new Array(Math.max(1, block.headers.length)).fill('')],
    });
  }

  removeTableRow(d: QuestionDraft, si: number, bi: number, ri: number): void {
    const block = d.sections[si].blocks[bi];
    this.updateBlock(d, si, bi, { rows: block.rows.filter((_, i) => i !== ri) });
  }

  addTableColumn(d: QuestionDraft, si: number, bi: number): void {
    const block = d.sections[si].blocks[bi];
    this.updateBlock(d, si, bi, {
      headers: [...block.headers, `Column ${block.headers.length + 1}`],
      rows: block.rows.map((row) => [...row, '']),
    });
  }

  removeTableColumn(d: QuestionDraft, si: number, bi: number, hi: number): void {
    const block = d.sections[si].blocks[bi];
    if (block.headers.length <= 1) return;
    this.updateBlock(d, si, bi, {
      headers: block.headers.filter((_, i) => i !== hi),
      rows: block.rows.map((row) => row.filter((_, i) => i !== hi)),
    });
  }

  togglePaste(d: QuestionDraft, si: number, bi: number): void {
    this.updateBlock(d, si, bi, { pasteOpen: !d.sections[si].blocks[bi].pasteOpen });
  }

  /** Import a table from pasted spreadsheet data; first line becomes the headers. */
  applyPastedTable(d: QuestionDraft, si: number, bi: number): void {
    const block = d.sections[si].blocks[bi];
    const lines = this.lines(block.pasteText);
    if (!lines.length) return;
    const split = (line: string) => (line.includes('\t') ? line.split('\t') : line.split(','));
    const parsed = lines.map((l) => split(l).map((c) => c.trim()));
    const width = Math.max(...parsed.map((r) => r.length));
    const padded = parsed.map((r) => [...r, ...new Array(width - r.length).fill('')]);
    let rows = padded.slice(1);
    if (!rows.length) rows = [new Array(width).fill('')];
    this.updateBlock(d, si, bi, { headers: padded[0], rows, pasteText: '', pasteOpen: false });
  }

  private serialize(d: QuestionDraft): { options: unknown; answer: unknown } | { error: string } {
    const kind = this.kindOf(d);

    if (kind === 'MCQ') {
      const options = this.lines(d.optionsText);
      if (options.length < 2) return { error: 'MCQ needs at least 2 options (one per line).' };
      const answer = d.answerText.trim();
      if (!answer) return { error: 'Enter the correct answer letter (e.g. C).' };
      return { options, answer };
    }
    if (kind === 'SATA') {
      const options = this.lines(d.optionsText);
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
      const rows = this.lines(d.matrixRowsText);
      const columns = this.lines(d.matrixColsText);
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
        const choices = this.lines(b.choicesText);
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
        const choices = this.lines(c.choicesText);
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
      const items = this.lines(d.rankingText);
      if (items.length < 2)
        return { error: 'RANKING needs at least 2 items (one per line, in correct order).' };
      // Display order intentionally differs from the correct order.
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

  // ── Type switching ──────────────────────────────────────────

  onTypeChange(d: QuestionDraft, type: string): void {
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
    this.updateDraft(d.id, patch);
  }

  // ── MATRIX helpers ──────────────────────────────────────────

  matrixRowLines(d: QuestionDraft): string[] {
    return this.lines(d.matrixRowsText);
  }

  matrixColLines(d: QuestionDraft): string[] {
    return this.lines(d.matrixColsText);
  }

  isMatrixAnswerChecked(d: QuestionDraft, rowIdx: number, col: string): boolean {
    return (d.matrixAnswer[String(rowIdx)] ?? []).includes(col);
  }

  toggleMatrixAnswer(d: QuestionDraft, rowIdx: number, col: string): void {
    const key = String(rowIdx);
    const matrixAnswer = { ...d.matrixAnswer };
    const sel = [...(matrixAnswer[key] ?? [])];
    const i = sel.indexOf(col);
    if (i >= 0) sel.splice(i, 1);
    else sel.push(col);
    if (sel.length) matrixAnswer[key] = sel;
    else delete matrixAnswer[key];
    this.updateDraft(d.id, { matrixAnswer });
  }

  // ── CLOZE helpers ───────────────────────────────────────────

  setClozeField<K extends keyof ClozeBlankDraft>(
    d: QuestionDraft,
    bi: number,
    key: K,
    value: ClozeBlankDraft[K],
  ): void {
    this.updateDraft(d.id, {
      clozeBlanks: d.clozeBlanks.map((b, i) => (i === bi ? { ...b, [key]: value } : b)),
    });
  }

  addClozeBlank(d: QuestionDraft): void {
    this.updateDraft(d.id, {
      clozeBlanks: [
        ...d.clozeBlanks,
        { label: `Blank ${d.clozeBlanks.length + 1}`, choicesText: '', answer: '' },
      ],
    });
  }

  removeClozeBlank(d: QuestionDraft, index: number): void {
    this.updateDraft(d.id, { clozeBlanks: d.clozeBlanks.filter((_, i) => i !== index) });
  }

  clozeChoiceLines(b: ClozeBlankDraft): string[] {
    return this.lines(b.choicesText);
  }

  // ── BOWTIE helpers ──────────────────────────────────────────

  setBowtieField<K extends keyof BowtieCategoryDraft>(
    d: QuestionDraft,
    ci: number,
    key: K,
    value: BowtieCategoryDraft[K],
  ): void {
    this.updateDraft(d.id, {
      bowtieCategories: d.bowtieCategories.map((c, i) => (i === ci ? { ...c, [key]: value } : c)),
    });
  }

  addBowtieCategory(d: QuestionDraft): void {
    this.updateDraft(d.id, {
      bowtieCategories: [
        ...d.bowtieCategories,
        {
          name: `Category ${d.bowtieCategories.length + 1}`,
          count: 1,
          choicesText: '',
          answer: [],
        },
      ],
    });
  }

  removeBowtieCategory(d: QuestionDraft, index: number): void {
    this.updateDraft(d.id, { bowtieCategories: d.bowtieCategories.filter((_, i) => i !== index) });
  }

  bowtieChoiceLines(c: BowtieCategoryDraft): string[] {
    return this.lines(c.choicesText);
  }

  isBowtieAnswer(c: BowtieCategoryDraft, choice: string): boolean {
    return c.answer.includes(choice);
  }

  toggleBowtieAnswer(d: QuestionDraft, ci: number, choice: string): void {
    const cat = d.bowtieCategories[ci];
    const answer = cat.answer.includes(choice)
      ? cat.answer.filter((a) => a !== choice)
      : [...cat.answer, choice];
    this.setBowtieField(d, ci, 'answer', answer);
  }

  // ── HIGHLIGHT helpers ───────────────────────────────────────

  setTokenText(d: QuestionDraft, ti: number, text: string): void {
    this.updateDraft(d.id, {
      highlightTokens: d.highlightTokens.map((t, i) => (i === ti ? { ...t, text } : t)),
    });
  }

  toggleTokenCorrect(d: QuestionDraft, ti: number): void {
    this.updateDraft(d.id, {
      highlightTokens: d.highlightTokens.map((t, i) =>
        i === ti ? { ...t, correct: !t.correct } : t,
      ),
    });
  }

  addHighlightToken(d: QuestionDraft): void {
    this.updateDraft(d.id, {
      highlightTokens: [...d.highlightTokens, { text: '', correct: false }],
    });
  }

  removeHighlightToken(d: QuestionDraft, index: number): void {
    this.updateDraft(d.id, { highlightTokens: d.highlightTokens.filter((_, i) => i !== index) });
  }

  // ── HOTSPOT region drawing ──────────────────────────────────

  private relativePercent(ev: MouseEvent, wrap: HTMLElement): { x: number; y: number } {
    const rect = wrap.getBoundingClientRect();
    const x = Math.min(100, Math.max(0, ((ev.clientX - rect.left) / rect.width) * 100));
    const y = Math.min(100, Math.max(0, ((ev.clientY - rect.top) / rect.height) * 100));
    return { x, y };
  }

  private currentDraft(id: number): QuestionDraft | undefined {
    return this.drafts().find((d) => d.id === id);
  }

  startRegionDraw(ev: MouseEvent, d: QuestionDraft, wrap: HTMLElement): void {
    if ((ev.target as HTMLElement).closest('.hs-region')) return;
    ev.preventDefault();
    const { x, y } = this.relativePercent(ev, wrap);
    const region: HotspotRegion = {
      id: `r${Date.now().toString(36)}`,
      label: `Region ${d.regions.length + 1}`,
      x,
      y,
      w: 0,
      h: 0,
    };
    this.updateDraft(d.id, { regions: [...d.regions, region] });
    this.drawing = { draftId: d.id, regionId: region.id, startX: x, startY: y };
  }

  moveRegionDraw(ev: MouseEvent, wrap: HTMLElement): void {
    if (!this.drawing) return;
    const { draftId, regionId, startX, startY } = this.drawing;
    const d = this.currentDraft(draftId);
    if (!d) return;
    const { x, y } = this.relativePercent(ev, wrap);
    this.updateDraft(draftId, {
      regions: d.regions.map((r) =>
        r.id === regionId
          ? {
              ...r,
              x: Math.min(startX, x),
              y: Math.min(startY, y),
              w: Math.abs(x - startX),
              h: Math.abs(y - startY),
            }
          : r,
      ),
    });
  }

  endRegionDraw(): void {
    if (!this.drawing) return;
    const { draftId, regionId } = this.drawing;
    this.drawing = null;
    const d = this.currentDraft(draftId);
    const region = d?.regions.find((r) => r.id === regionId);
    if (!d || !region) return;
    // Discard accidental clicks (tiny regions)
    if (region.w < 2 || region.h < 2) {
      this.updateDraft(draftId, { regions: d.regions.filter((r) => r.id !== regionId) });
    } else if (!d.hotspotAnswer) {
      this.updateDraft(draftId, { hotspotAnswer: regionId });
    }
  }

  setRegionLabel(d: QuestionDraft, ri: number, label: string): void {
    this.updateDraft(d.id, {
      regions: d.regions.map((r, i) => (i === ri ? { ...r, label } : r)),
    });
  }

  removeRegion(d: QuestionDraft, index: number): void {
    const removed = d.regions[index];
    this.updateDraft(d.id, {
      regions: d.regions.filter((_, i) => i !== index),
      hotspotAnswer: removed && d.hotspotAnswer === removed.id ? '' : d.hotspotAnswer,
    });
  }

  addManualRegion(d: QuestionDraft): void {
    this.updateDraft(d.id, {
      regions: [
        ...d.regions,
        {
          id: `r${Date.now().toString(36)}`,
          label: `Region ${d.regions.length + 1}`,
          x: 10,
          y: 10,
          w: 30,
          h: 20,
        },
      ],
    });
  }

  // ── Image upload ────────────────────────────────────────────

  onImageSelected(event: Event, d: QuestionDraft): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.setFlag(this.uploading, d.id, true);
    this.setError(d.id, '');
    this.examService.uploadQuestionImage(d.id, file).subscribe({
      next: (res) => {
        this.updateDraft(d.id, { image: res.image });
        this.setFlag(this.uploading, d.id, false);
      },
      error: (err) => {
        this.setFlag(this.uploading, d.id, false);
        this.setError(d.id, err?.error?.detail || 'Image upload failed.');
      },
    });
    input.value = '';
  }

  removeImage(d: QuestionDraft): void {
    this.examService.deleteQuestionImage(d.id).subscribe({
      next: () => this.updateDraft(d.id, { image: null }),
      error: () => this.setError(d.id, 'Could not remove the image.'),
    });
  }

  // ── Save / delete / add ─────────────────────────────────────

  save(clicked: QuestionDraft): void {
    // Re-read the current draft — the object captured at click time may predate the
    // latest copy-on-write replacement.
    const d = this.currentDraft(clicked.id) ?? clicked;
    this.setError(d.id, '');
    if (!d.question.trim()) {
      this.setError(d.id, 'Question text cannot be empty.');
      return;
    }
    const serialized = this.serialize(d);
    if ('error' in serialized) {
      this.setError(d.id, serialized.error);
      return;
    }
    this.setFlag(this.saving, d.id, true);
    this.examService
      .updateQuestion(this.examId, d.id, {
        number: d.number,
        topic: d.topic,
        type: d.type,
        question: d.question,
        sections: this.serializeSections(d),
        rationale: d.rationale,
        options: serialized.options as never,
        answer: serialized.answer as never,
      })
      .subscribe({
        next: () => {
          this.setFlag(this.saving, d.id, false);
          this.setFlag(this.saved, d.id, true);
          const existing = this.savedTimers.get(d.id);
          if (existing) clearTimeout(existing);
          this.savedTimers.set(
            d.id,
            setTimeout(() => this.setFlag(this.saved, d.id, false), 2000),
          );
        },
        error: (err) => {
          this.setFlag(this.saving, d.id, false);
          this.setError(d.id, err?.error?.detail || 'Save failed.');
        },
      });
  }

  deleteQuestion(d: QuestionDraft): void {
    if (!confirm(`Delete question #${d.number}? This cannot be undone.`)) return;
    this.examService.deleteQuestion(this.examId, d.id).subscribe({
      next: () => this.drafts.update((list) => list.filter((x) => x.id !== d.id)),
      error: (err) => this.setError(d.id, err?.error?.detail || 'Delete failed.'),
    });
  }

  addQuestion(): void {
    this.addingQuestion.set(true);
    const nextNumber = Math.max(0, ...this.drafts().map((d) => d.number)) + 1;
    this.examService
      .addQuestion(this.examId, {
        number: nextNumber,
        topic: '',
        type: 'MCQ',
        question: 'New question',
        options: ['A. Option 1', 'B. Option 2', 'C. Option 3', 'D. Option 4'],
        answer: 'A',
        rationale: '',
      })
      .subscribe({
        next: (q) => {
          const draft = this.toDraft(q);
          this.drafts.update((list) => [...list, draft]);
          this.expanded.set({ ...this.expanded(), [draft.id]: true });
          this.addingQuestion.set(false);
        },
        error: (err) => {
          this.addingQuestion.set(false);
          alert(err?.error?.detail || 'Could not add a question.');
        },
      });
  }
}
