import { Component, OnInit, signal } from '@angular/core';

import { AdminTabsComponent } from '../../components/admin-tabs/admin-tabs';
import { httpErrorDetail, ExamService, SystemInfo, formatBytes, formatDate } from '../../services/exam.service';

/**
 * Deployment status: environment, database, disk and backups.
 *
 * The backup panel reports names, sizes and timestamps only. The dumps hold every
 * password hash and answer key in the deployment, so the API deliberately has no
 * route that reads one, and there is nothing to download here.
 */
@Component({
  selector: 'app-admin-system',
  imports: [AdminTabsComponent],
  templateUrl: './admin-system.html',
  styleUrl: './admin-system.scss',
})
export class AdminSystemPage implements OnInit {
  info = signal<SystemInfo | null>(null);
  loading = signal(true);
  loadError = signal('');

  readonly formatBytes = formatBytes;
  readonly formatDate = formatDate;

  constructor(private examService: ExamService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.examService.getSystemInfo().subscribe({
      next: (info) => {
        this.info.set(info);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(httpErrorDetail(err) || 'Failed to load system status.');
      },
    });
  }

  /** How stale the newest backup is, in whole hours or days. */
  backupAge(iso: string): string {
    const hours = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
    if (hours < 1) return 'less than an hour ago';
    if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
    const days = Math.floor(hours / 24);
    return `${days} day${days === 1 ? '' : 's'} ago`;
  }

  /** The sidecar runs daily, so anything past ~36h means it is not running. */
  backupIsStale(iso: string): boolean {
    return Date.now() - new Date(iso).getTime() > 36 * 3_600_000;
  }
}
