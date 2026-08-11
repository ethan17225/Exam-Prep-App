import { Component, computed, input, signal } from '@angular/core';
import {
  ListBlock,
  QuestionSection,
  SectionBlock,
  TableBlock,
  TextBlock,
} from '../../services/exam.service';

/**
 * Renders the supporting patient data attached to a question.
 * Multiple sections display as a tabbed chart; a single section renders as one panel.
 */
@Component({
  selector: 'app-question-sections',
  imports: [],
  templateUrl: './question-sections.html',
  styleUrl: './question-sections.scss',
})
export class QuestionSectionsComponent {
  sections = input<QuestionSection[] | null | undefined>(null);
  /** Collapsed by default in dense review lists. */
  startCollapsed = input(false);

  activeIndex = signal(0);
  private manuallyToggled = signal(false);

  visibleSections = computed(() => {
    const list = this.sections();
    if (!Array.isArray(list)) return [];
    return list.filter((s) => s && Array.isArray(s.blocks) && s.blocks.length > 0);
  });

  hasSections = computed(() => this.visibleSections().length > 0);
  isTabbed = computed(() => this.visibleSections().length > 1);

  expanded = computed(() => (this.manuallyToggled() ? this.userExpanded() : !this.startCollapsed()));
  private userExpanded = signal(true);

  activeSection = computed(() => {
    const list = this.visibleSections();
    const i = Math.min(this.activeIndex(), Math.max(0, list.length - 1));
    return list[i] ?? null;
  });

  selectTab(index: number): void {
    this.activeIndex.set(index);
  }

  toggleExpanded(): void {
    this.userExpanded.set(!this.expanded());
    this.manuallyToggled.set(true);
  }

  isText(block: SectionBlock): block is TextBlock {
    return block.type === 'text';
  }

  isList(block: SectionBlock): block is ListBlock {
    return block.type === 'list';
  }

  isTable(block: SectionBlock): block is TableBlock {
    return block.type === 'table';
  }

  asText(block: SectionBlock): TextBlock {
    return block as TextBlock;
  }

  asList(block: SectionBlock): ListBlock {
    return block as ListBlock;
  }

  asTable(block: SectionBlock): TableBlock {
    return block as TableBlock;
  }

  tableHeaders(block: SectionBlock): string[] {
    return (block as TableBlock).headers ?? [];
  }

  tableRows(block: SectionBlock): string[][] {
    return (block as TableBlock).rows ?? [];
  }

  listItems(block: SectionBlock): string[] {
    return (block as ListBlock).items ?? [];
  }
}
