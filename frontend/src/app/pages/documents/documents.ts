import { Component, HostListener, OnInit, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ExamService, Course, DocumentItem } from '../../services/exam.service';

@Component({
  selector: 'app-documents',
  imports: [FormsModule],
  templateUrl: './documents.html',
  styleUrl: './documents.scss',
})
export class DocumentsPage implements OnInit {
  courses = signal<Course[]>([]);
  documents = signal<DocumentItem[]>([]);
  selectedCourseId = signal<string>('');
  searchQuery = signal('');

  loading = signal(true);
  loadError = signal('');

  // Viewer state
  viewingDoc = signal<DocumentItem | null>(null);
  viewingHtml = signal<string | null>(null);
  viewerLoading = signal(false);
  viewerError = signal('');

  /** Group documents by course_name for display */
  groupedDocuments = computed(() => {
    const courseId = this.selectedCourseId();
    const query = this.searchQuery().toLowerCase().trim();
    let docs = this.documents();

    if (courseId) {
      docs = docs.filter((d) => d.course_id === courseId);
    }

    if (query) {
      docs = docs.filter((d) => d.title.toLowerCase().includes(query));
    }

    const groups: { courseName: string; docs: DocumentItem[] }[] = [];
    const map = new Map<string, DocumentItem[]>();

    for (const doc of docs) {
      const key = doc.course_name ?? 'Uncategorized';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(doc);
    }

    for (const [courseName, courseDocs] of map) {
      groups.push({ courseName, docs: courseDocs });
    }

    return groups;
  });

  constructor(private examService: ExamService) {}

  ngOnInit(): void {
    // The course filter is a convenience — the document list itself surfaces load failures.
    this.examService.listCourses().subscribe((data) => this.courses.set(data));
    this.loadDocuments();
  }

  loadDocuments(): void {
    this.loadError.set('');
    this.examService.listDocuments().subscribe({
      next: (data) => {
        this.documents.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Failed to load documents.');
      },
    });
  }

  onCourseChange(courseId: string): void {
    this.selectedCourseId.set(courseId);
  }

  openDoc(doc: DocumentItem): void {
    this.viewingDoc.set(doc);
    this.viewingHtml.set(null);
    this.viewerLoading.set(true);
    this.viewerError.set('');

    if (!doc.html_url) {
      this.viewerError.set('No HTML version available for this document.');
      this.viewerLoading.set(false);
      return;
    }

    this.examService.getDocumentContent(doc.html_url).subscribe({
      next: (content) => {
        // Bound as a plain string so Angular's sanitizer runs on it. The server
        // only strips the <body> wrapper — it does not sanitize — and these files
        // are served from our own origin, so bypassing sanitization here would
        // make any document a same-origin script injection.
        this.viewingHtml.set(content.html);
        this.viewerLoading.set(false);
      },
      error: () => {
        this.viewerError.set('Failed to load document content.');
        this.viewerLoading.set(false);
      },
    });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.viewingDoc()) this.closeViewer();
  }

  closeViewer(): void {
    this.viewingDoc.set(null);
    this.viewingHtml.set(null);
    this.viewerError.set('');
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
}
