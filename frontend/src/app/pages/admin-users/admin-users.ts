import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { Observable } from 'rxjs';

import { AdminTabsComponent } from '../../components/admin-tabs/admin-tabs';
import {
  AdminInstructor,
  AdminUser,
  AdminUserCreate,
  AdminUserDetail,
  ExamService,
  formatDate,
  formatDuration,
  formatRole,
} from '../../services/exam.service';
import { AuthService, UserRole, initialsOf } from '../../services/auth.service';

const PAGE_SIZE = 25;

/** A blank create form. A function, not a constant — the object is mutated by ngModel. */
function emptyDraft(): AdminUserCreate {
  return { email: '', password: '', role: 'student', display_name: '', instructor_id: '' };
}

/**
 * Account management: search, create, inspect, re-role, reset, delete.
 *
 * Paginated server-side rather than filtered in the browser like the instructor's
 * Students page — that page holds one class, this one holds every account in the
 * deployment.
 */
@Component({
  selector: 'app-admin-users',
  imports: [FormsModule, AdminTabsComponent],
  templateUrl: './admin-users.html',
  styleUrl: './admin-users.scss',
})
export class AdminUsersPage implements OnInit {
  users = signal<AdminUser[]>([]);
  total = signal(0);
  offset = signal(0);
  loading = signal(true);
  loadError = signal('');

  search = signal('');
  roleFilter = signal<UserRole | ''>('');

  /** Staff, for the enrolment and transfer pickers. Loaded once. */
  instructors = signal<AdminInstructor[]>([]);

  // ── Create form ──
  showCreate = signal(false);
  draft = signal<AdminUserCreate>(emptyDraft());
  creating = signal(false);
  createError = signal('');

  // ── Expanded row ──
  expandedId = signal<string | null>(null);
  detail = signal<AdminUserDetail | null>(null);
  detailLoading = signal(false);
  detailError = signal('');

  // Per-row state keyed by id, not one global flag: several rows can be mid-action
  // and a shared flag would spin every button at once.
  rowBusy = signal<Record<string, boolean>>({});
  rowError = signal<Record<string, string>>({});
  rowNotice = signal<Record<string, string>>({});
  passwordDrafts = signal<Record<string, string>>({});

  readonly formatDate = formatDate;
  readonly formatDuration = formatDuration;
  readonly formatRole = formatRole;
  readonly initialsOf = initialsOf;
  readonly pageSize = PAGE_SIZE;
  readonly roles: UserRole[] = ['student', 'instructor', 'admin'];

  constructor(
    private examService: ExamService,
    private auth: AuthService,
    private route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    // The dashboard's KPI cards link here with ?role=, so honour it on first load.
    const role = this.route.snapshot.queryParamMap.get('role');
    if (role === 'student' || role === 'instructor' || role === 'admin') this.roleFilter.set(role);
    this.load();
    this.loadInstructors();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService
      .listAdminUsers(this.search().trim(), this.roleFilter(), PAGE_SIZE, this.offset())
      .subscribe({
        next: (page) => {
          this.users.set(page.items);
          this.total.set(page.total);
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          this.loadError.set(err?.error?.detail || 'Failed to load accounts.');
        },
      });
  }

  private loadInstructors(): void {
    // Cosmetic on failure: the pickers fall back to empty and the page still works.
    this.examService.listAdminInstructors().subscribe({
      next: (rows) => this.instructors.set(rows),
      error: () => {},
    });
  }

  /** Any filter change resets to the first page, or the view can land past the end. */
  applyFilters(): void {
    this.offset.set(0);
    this.collapse();
    this.load();
  }

  setRoleFilter(role: UserRole | ''): void {
    this.roleFilter.set(role);
    this.applyFilters();
  }

  page(delta: number): void {
    const next = this.offset() + delta * PAGE_SIZE;
    if (next < 0 || next >= this.total()) return;
    this.offset.set(next);
    this.collapse();
    this.load();
  }

  /** 1-based range for "Showing 1-25 of 61". */
  rangeStart(): number {
    return this.total() === 0 ? 0 : this.offset() + 1;
  }

  rangeEnd(): number {
    return Math.min(this.offset() + PAGE_SIZE, this.total());
  }

  isSelf(user: AdminUser): boolean {
    return this.auth.user()?.id === user.id;
  }

  // ── Create ────────────────────────────────────────────────────

  toggleCreate(): void {
    this.showCreate.update((open) => !open);
    this.draft.set(emptyDraft());
    this.createError.set('');
  }

  /** Copy-on-write so the template's computed reads recompute. */
  patchDraft(patch: Partial<AdminUserCreate>): void {
    this.draft.set({ ...this.draft(), ...patch });
  }

  create(): void {
    const draft = this.draft();
    this.creating.set(true);
    this.createError.set('');
    this.examService
      .createAdminUser({
        email: draft.email.trim(),
        password: draft.password,
        role: draft.role,
        display_name: draft.display_name?.trim() || null,
        // Sent only for a student; the server ignores it for staff anyway, but
        // an empty string would read as a real id.
        instructor_id: draft.role === 'student' ? draft.instructor_id || null : null,
      })
      .subscribe({
        next: () => {
          this.creating.set(false);
          this.showCreate.set(false);
          this.draft.set(emptyDraft());
          this.load();
          this.loadInstructors();
        },
        error: (err) => {
          this.creating.set(false);
          this.createError.set(err?.error?.detail || 'Failed to create the account.');
        },
      });
  }

  // ── Row detail ────────────────────────────────────────────────

  toggle(user: AdminUser): void {
    if (this.expandedId() === user.id) {
      this.collapse();
      return;
    }

    this.expandedId.set(user.id);
    this.detail.set(null);
    this.detailError.set('');
    this.detailLoading.set(true);
    this.examService.getAdminUser(user.id).subscribe({
      next: (detail) => {
        // Ignore a response that arrived after the user moved on to another row.
        if (this.expandedId() !== user.id) return;
        this.detail.set(detail);
        this.detailLoading.set(false);
      },
      error: (err) => {
        if (this.expandedId() !== user.id) return;
        this.detailLoading.set(false);
        this.detailError.set(err?.error?.detail || 'Failed to load this account.');
      },
    });
  }

  private collapse(): void {
    this.expandedId.set(null);
    this.detail.set(null);
  }

  // ── Row actions ───────────────────────────────────────────────

  changeRole(user: AdminUser, role: UserRole): void {
    if (role === user.role) return;
    // The server refuses this too; asking first is what makes it legible rather
    // than a surprise 409.
    if (this.isSelf(user)) {
      this.setRowError(user.id, 'You cannot change your own role.');
      return;
    }
    const label = user.display_name || user.email;
    if (!confirm(`Change ${label} from ${user.role} to ${role}? This signs them out everywhere.`)) {
      return;
    }
    this.run(user.id, this.examService.updateAdminUser(user.id, { role }), 'Role updated.');
  }

  enrolWith(user: AdminUser, instructorId: string): void {
    if (!instructorId || instructorId === user.instructor_id) return;
    this.run(
      user.id,
      this.examService.updateAdminUser(user.id, { instructor_id: instructorId }),
      'Enrolment updated.',
    );
  }

  setPasswordDraft(userId: string, value: string): void {
    this.passwordDrafts.set({ ...this.passwordDrafts(), [userId]: value });
  }

  resetPassword(user: AdminUser): void {
    const password = this.passwordDrafts()[user.id] ?? '';
    if (password.length < 8) {
      this.setRowError(user.id, 'Password must be at least 8 characters.');
      return;
    }
    this.run(
      user.id,
      this.examService.resetUserPassword(user.id, password),
      'Password reset. All their sessions were signed out.',
      () => this.setPasswordDraft(user.id, ''),
    );
  }

  revokeSessions(user: AdminUser): void {
    const label = user.display_name || user.email;
    if (!confirm(`Sign ${label} out of every device?`)) return;
    this.run(user.id, this.examService.revokeUserSessions(user.id), 'Signed out everywhere.');
  }

  rotateCode(user: AdminUser): void {
    if (!confirm('Issue a new enrolment code? The old one stops working immediately.')) return;
    this.run(user.id, this.examService.rotateInviteCode(user.id), 'New enrolment code issued.');
  }

  reassign(user: AdminUser, toInstructorId: string): void {
    if (!toInstructorId) return;
    const label = user.display_name || user.email;
    if (!confirm(`Move every student of ${label} to the selected instructor?`)) return;
    this.run(
      user.id,
      this.examService.reassignStudents(user.id, toInstructorId),
      'Students moved.',
    );
  }

  remove(user: AdminUser): void {
    const label = user.display_name || user.email;
    // Spelled out because it is irreversible and wider than it looks: the cascade
    // takes their exams, questions and marks with them.
    const warning =
      `Permanently delete ${label}?\n\n` +
      `This also deletes their courses, exams, questions and attempt history. ` +
      (user.student_count > 0
        ? `Their ${user.student_count} student(s) are unenrolled, not deleted.\n\n`
        : '\n') +
      `This cannot be undone.`;
    if (!confirm(warning)) return;
    this.run(user.id, this.examService.deleteAdminUser(user.id), '', () => {
      this.collapse();
      this.load();
      this.loadInstructors();
    });
  }

  /**
   * One place for the busy/error/notice bookkeeping every row action shares.
   * Refetches the list on success rather than patching the row, matching the
   * refetch-after-mutate idiom used everywhere else.
   */
  private run(
    userId: string,
    request: Observable<unknown>,
    notice: string,
    onSuccess?: () => void,
  ): void {
    this.setRowBusy(userId, true);
    this.setRowError(userId, '');
    this.setRowNotice(userId, '');
    request.subscribe({
      next: () => {
        this.setRowBusy(userId, false);
        if (notice) this.setRowNotice(userId, notice);
        if (onSuccess) {
          onSuccess();
        } else {
          this.load();
          if (this.expandedId() === userId) this.refreshDetail(userId);
        }
      },
      error: (err: { error?: { detail?: string } }) => {
        this.setRowBusy(userId, false);
        this.setRowError(userId, err?.error?.detail || 'That action failed.');
      },
    });
  }

  private refreshDetail(userId: string): void {
    this.examService.getAdminUser(userId).subscribe({
      next: (detail) => {
        if (this.expandedId() === userId) this.detail.set(detail);
      },
      error: () => {},
    });
  }

  private setRowBusy(userId: string, busy: boolean): void {
    this.rowBusy.set({ ...this.rowBusy(), [userId]: busy });
  }

  private setRowError(userId: string, message: string): void {
    this.rowError.set({ ...this.rowError(), [userId]: message });
  }

  private setRowNotice(userId: string, message: string): void {
    this.rowNotice.set({ ...this.rowNotice(), [userId]: message });
  }
}
