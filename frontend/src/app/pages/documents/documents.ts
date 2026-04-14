import { Component, OnInit, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
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

  // Viewer state
  viewingDoc = signal<DocumentItem | null>(null);
  viewingHtml = signal<SafeHtml | null>(null);
  viewerLoading = signal(false);
  viewerError = signal('');

  /** Group documents by course_name for display */
  groupedDocuments = computed(() => {
    const courseId = this.selectedCourseId();
    let docs = this.documents();
    if (courseId) {
      docs = docs.filter((d) => d.course_id === courseId);
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

  constructor(
    private examService: ExamService,
    private sanitizer: DomSanitizer,
  ) {}

  ngOnInit(): void {
    this.examService.listCourses().subscribe((data) => this.courses.set(data));
    this.loadDocuments();
  }

  loadDocuments(): void {
    this.examService.listDocuments().subscribe((data) => this.documents.set(data));
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
        this.viewingHtml.set(this.sanitizer.bypassSecurityTrustHtml(content.html));
        this.viewerLoading.set(false);
      },
      error: () => {
        this.viewerError.set('Failed to load document content.');
        this.viewerLoading.set(false);
      },
    });
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
