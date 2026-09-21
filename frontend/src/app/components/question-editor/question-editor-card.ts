import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HotspotRegion } from '../../services/exam.service';
import {
  BlockKind,
  BowtieCategoryDraft,
  ClozeBlankDraft,
  QuestionDraft,
  SectionBlockDraft,
  SectionDraft,
  QUESTION_TYPES,
  kindOf,
  lines,
  newBlockDraft,
  preview,
  typeChangePatch,
} from './question-draft';

@Component({
  selector: 'app-question-editor-card',
  imports: [FormsModule],
  templateUrl: './question-editor-card.html',
  styleUrl: './question-editor-card.scss',
})
export class QuestionEditorCardComponent {
  draft = input.required<QuestionDraft>();
  index = input(0);
  expanded = input(false);
  saving = input(false);
  saved = input(false);
  uploading = input(false);
  error = input('');

  expandToggle = output<void>();
  draftChange = output<QuestionDraft>();
  save = output<QuestionDraft>();
  remove = output<QuestionDraft>();
  imageFile = output<File>();
  removeImage = output<void>();

  readonly questionTypes = QUESTION_TYPES;

  private drawing: { regionId: string; startX: number; startY: number } | null = null;

  kind(): ReturnType<typeof kindOf> {
    return kindOf(this.draft());
  }

  previewText(): string {
    return preview(this.draft());
  }

  private emit(patch: Partial<QuestionDraft>): void {
    this.draftChange.emit({ ...this.draft(), ...patch });
  }

  setField<K extends keyof QuestionDraft>(key: K, value: QuestionDraft[K]): void {
    this.emit({ [key]: value } as Partial<QuestionDraft>);
  }

  onTypeChange(type: string): void {
    this.emit(typeChangePatch(this.draft(), type));
  }

  private updateSection(si: number, patch: Partial<SectionDraft>): void {
    const d = this.draft();
    this.emit({
      sections: d.sections.map((s, i) => (i === si ? { ...s, ...patch } : s)),
    });
  }

  setSectionTitle(si: number, title: string): void {
    this.updateSection(si, { title });
  }

  addSection(): void {
    const d = this.draft();
    this.emit({
      sections: [
        ...d.sections,
        {
          title: `Tab ${d.sections.length + 1}`,
          collapsed: false,
          blocks: [newBlockDraft('text')],
        },
      ],
    });
  }

  removeSection(si: number): void {
    this.emit({ sections: this.draft().sections.filter((_, i) => i !== si) });
  }

  moveSection(si: number, delta: number): void {
    const target = si + delta;
    const sections = [...this.draft().sections];
    if (target < 0 || target >= sections.length) return;
    [sections[si], sections[target]] = [sections[target], sections[si]];
    this.emit({ sections });
  }

  toggleSection(si: number): void {
    this.updateSection(si, { collapsed: !this.draft().sections[si].collapsed });
  }

  private updateBlock(si: number, bi: number, patch: Partial<SectionBlockDraft>): void {
    const section = this.draft().sections[si];
    this.updateSection(si, {
      blocks: section.blocks.map((b, i) => (i === bi ? { ...b, ...patch } : b)),
    });
  }

  setBlockField<K extends keyof SectionBlockDraft>(
    si: number,
    bi: number,
    key: K,
    value: SectionBlockDraft[K],
  ): void {
    this.updateBlock(si, bi, { [key]: value } as Partial<SectionBlockDraft>);
  }

  addBlock(si: number, kind: BlockKind): void {
    const section = this.draft().sections[si];
    this.updateSection(si, { blocks: [...section.blocks, newBlockDraft(kind)] });
  }

  removeBlock(si: number, bi: number): void {
    const section = this.draft().sections[si];
    this.updateSection(si, { blocks: section.blocks.filter((_, i) => i !== bi) });
  }

  moveBlock(si: number, bi: number, delta: number): void {
    const blocks = [...this.draft().sections[si].blocks];
    const target = bi + delta;
    if (target < 0 || target >= blocks.length) return;
    [blocks[bi], blocks[target]] = [blocks[target], blocks[bi]];
    this.updateSection(si, { blocks });
  }

  setHeader(si: number, bi: number, hi: number, value: string): void {
    const block = this.draft().sections[si].blocks[bi];
    this.updateBlock(si, bi, { headers: block.headers.map((h, i) => (i === hi ? value : h)) });
  }

  setCell(si: number, bi: number, ri: number, ci: number, value: string): void {
    const block = this.draft().sections[si].blocks[bi];
    this.updateBlock(si, bi, {
      rows: block.rows.map((row, r) =>
        r === ri ? row.map((c, i) => (i === ci ? value : c)) : row,
      ),
    });
  }

  addTableRow(si: number, bi: number): void {
    const block = this.draft().sections[si].blocks[bi];
    this.updateBlock(si, bi, {
      rows: [...block.rows, new Array(Math.max(1, block.headers.length)).fill('')],
    });
  }

  removeTableRow(si: number, bi: number, ri: number): void {
    const block = this.draft().sections[si].blocks[bi];
    this.updateBlock(si, bi, { rows: block.rows.filter((_, i) => i !== ri) });
  }

  addTableColumn(si: number, bi: number): void {
    const block = this.draft().sections[si].blocks[bi];
    this.updateBlock(si, bi, {
      headers: [...block.headers, `Column ${block.headers.length + 1}`],
      rows: block.rows.map((row) => [...row, '']),
    });
  }

  removeTableColumn(si: number, bi: number, hi: number): void {
    const block = this.draft().sections[si].blocks[bi];
    if (block.headers.length <= 1) return;
    this.updateBlock(si, bi, {
      headers: block.headers.filter((_, i) => i !== hi),
      rows: block.rows.map((row) => row.filter((_, i) => i !== hi)),
    });
  }

  togglePaste(si: number, bi: number): void {
    this.updateBlock(si, bi, { pasteOpen: !this.draft().sections[si].blocks[bi].pasteOpen });
  }

  applyPastedTable(si: number, bi: number): void {
    const block = this.draft().sections[si].blocks[bi];
    const parsedLines = lines(block.pasteText);
    if (!parsedLines.length) return;
    const split = (line: string) => (line.includes('\t') ? line.split('\t') : line.split(','));
    const parsed = parsedLines.map((l) => split(l).map((c) => c.trim()));
    const width = Math.max(...parsed.map((r) => r.length));
    const padded = parsed.map((r) => [...r, ...new Array(width - r.length).fill('')]);
    let rows = padded.slice(1);
    if (!rows.length) rows = [new Array(width).fill('')];
    this.updateBlock(si, bi, { headers: padded[0], rows, pasteText: '', pasteOpen: false });
  }

  matrixRowLines(): string[] {
    return lines(this.draft().matrixRowsText);
  }

  matrixColLines(): string[] {
    return lines(this.draft().matrixColsText);
  }

  isMatrixAnswerChecked(rowIdx: number, col: string): boolean {
    return (this.draft().matrixAnswer[String(rowIdx)] ?? []).includes(col);
  }

  toggleMatrixAnswer(rowIdx: number, col: string): void {
    const key = String(rowIdx);
    const matrixAnswer = { ...this.draft().matrixAnswer };
    const sel = [...(matrixAnswer[key] ?? [])];
    const i = sel.indexOf(col);
    if (i >= 0) sel.splice(i, 1);
    else sel.push(col);
    if (sel.length) matrixAnswer[key] = sel;
    else delete matrixAnswer[key];
    this.emit({ matrixAnswer });
  }

  setClozeField<K extends keyof ClozeBlankDraft>(
    bi: number,
    key: K,
    value: ClozeBlankDraft[K],
  ): void {
    this.emit({
      clozeBlanks: this.draft().clozeBlanks.map((b, i) => (i === bi ? { ...b, [key]: value } : b)),
    });
  }

  addClozeBlank(): void {
    const d = this.draft();
    this.emit({
      clozeBlanks: [
        ...d.clozeBlanks,
        { label: `Blank ${d.clozeBlanks.length + 1}`, choicesText: '', answer: '' },
      ],
    });
  }

  removeClozeBlank(index: number): void {
    this.emit({ clozeBlanks: this.draft().clozeBlanks.filter((_, i) => i !== index) });
  }

  clozeChoiceLines(b: ClozeBlankDraft): string[] {
    return lines(b.choicesText);
  }

  setBowtieField<K extends keyof BowtieCategoryDraft>(
    ci: number,
    key: K,
    value: BowtieCategoryDraft[K],
  ): void {
    this.emit({
      bowtieCategories: this.draft().bowtieCategories.map((c, i) =>
        i === ci ? { ...c, [key]: value } : c,
      ),
    });
  }

  addBowtieCategory(): void {
    const d = this.draft();
    this.emit({
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

  removeBowtieCategory(index: number): void {
    this.emit({
      bowtieCategories: this.draft().bowtieCategories.filter((_, i) => i !== index),
    });
  }

  bowtieChoiceLines(c: BowtieCategoryDraft): string[] {
    return lines(c.choicesText);
  }

  isBowtieAnswer(c: BowtieCategoryDraft, choice: string): boolean {
    return c.answer.includes(choice);
  }

  toggleBowtieAnswer(ci: number, choice: string): void {
    const cat = this.draft().bowtieCategories[ci];
    const answer = cat.answer.includes(choice)
      ? cat.answer.filter((a) => a !== choice)
      : [...cat.answer, choice];
    this.setBowtieField(ci, 'answer', answer);
  }

  setTokenText(ti: number, text: string): void {
    this.emit({
      highlightTokens: this.draft().highlightTokens.map((t, i) => (i === ti ? { ...t, text } : t)),
    });
  }

  toggleTokenCorrect(ti: number): void {
    this.emit({
      highlightTokens: this.draft().highlightTokens.map((t, i) =>
        i === ti ? { ...t, correct: !t.correct } : t,
      ),
    });
  }

  addHighlightToken(): void {
    this.emit({
      highlightTokens: [...this.draft().highlightTokens, { text: '', correct: false }],
    });
  }

  removeHighlightToken(index: number): void {
    this.emit({
      highlightTokens: this.draft().highlightTokens.filter((_, i) => i !== index),
    });
  }

  private relativePercent(ev: MouseEvent, wrap: HTMLElement): { x: number; y: number } {
    const rect = wrap.getBoundingClientRect();
    const x = Math.min(100, Math.max(0, ((ev.clientX - rect.left) / rect.width) * 100));
    const y = Math.min(100, Math.max(0, ((ev.clientY - rect.top) / rect.height) * 100));
    return { x, y };
  }

  startRegionDraw(ev: MouseEvent, wrap: HTMLElement): void {
    if ((ev.target as HTMLElement).closest('.hs-region')) return;
    ev.preventDefault();
    const d = this.draft();
    const { x, y } = this.relativePercent(ev, wrap);
    const region: HotspotRegion = {
      id: `r${Date.now().toString(36)}`,
      label: `Region ${d.regions.length + 1}`,
      x,
      y,
      w: 0,
      h: 0,
    };
    this.emit({ regions: [...d.regions, region] });
    this.drawing = { regionId: region.id, startX: x, startY: y };
  }

  moveRegionDraw(ev: MouseEvent, wrap: HTMLElement): void {
    if (!this.drawing) return;
    const { regionId, startX, startY } = this.drawing;
    const d = this.draft();
    const { x, y } = this.relativePercent(ev, wrap);
    this.emit({
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
    const { regionId } = this.drawing;
    this.drawing = null;
    const d = this.draft();
    const region = d.regions.find((r) => r.id === regionId);
    if (!region) return;
    if (region.w < 2 || region.h < 2) {
      this.emit({ regions: d.regions.filter((r) => r.id !== regionId) });
    } else if (!d.hotspotAnswer) {
      this.emit({ hotspotAnswer: regionId });
    }
  }

  setRegionLabel(ri: number, label: string): void {
    this.emit({
      regions: this.draft().regions.map((r, i) => (i === ri ? { ...r, label } : r)),
    });
  }

  removeRegion(index: number): void {
    const d = this.draft();
    const removed = d.regions[index];
    this.emit({
      regions: d.regions.filter((_, i) => i !== index),
      hotspotAnswer: removed && d.hotspotAnswer === removed.id ? '' : d.hotspotAnswer,
    });
  }

  addManualRegion(): void {
    const d = this.draft();
    this.emit({
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

  onFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) this.imageFile.emit(file);
    input.value = '';
  }
}
