import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService, initialsOf } from '../../services/auth.service';

@Component({
  selector: 'app-onboarding',
  imports: [FormsModule],
  templateUrl: './onboarding.html',
  styleUrl: './onboarding.scss',
})
export class OnboardingPage implements OnInit, OnDestroy {
  displayName = signal('');
  error = signal('');
  saving = signal(false);

  /** The chosen file, held until the name is saved so one failure loses nothing. */
  private pending: File | null = null;
  previewUrl = signal<string | null>(null);
  avatarError = signal('');

  constructor(
    private auth: AuthService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    // Already onboarded, so there is nothing to collect. Reachable by typing the
    // URL, since the guard deliberately lets this route through unconditionally.
    if (!this.auth.needsOnboarding()) {
      this.router.navigateByUrl('/overview');
      return;
    }
    // Seed from the email local part so the common case is one click.
    const email = this.auth.user()?.email ?? '';
    this.displayName.set(email.split('@')[0] ?? '');
  }

  ngOnDestroy(): void {
    this.revokePreview();
  }

  initials(): string {
    return initialsOf({ display_name: this.displayName(), email: this.auth.user()?.email ?? '' });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.avatarError.set('');
    this.pending = file;
    this.revokePreview();
    this.previewUrl.set(URL.createObjectURL(file));
  }

  clearImage(): void {
    this.pending = null;
    this.revokePreview();
    this.previewUrl.set(null);
    this.avatarError.set('');
  }

  submit(): void {
    const name = this.displayName().trim();
    if (!name) {
      this.error.set('Please enter a preferred name.');
      return;
    }

    this.saving.set(true);
    this.error.set('');
    this.auth.updateProfile(name).subscribe({
      next: () => this.uploadThenFinish(),
      error: (err) => {
        this.saving.set(false);
        this.error.set(err?.error?.detail || 'Could not save your name.');
      },
    });
  }

  /**
   * The image is optional, so a rejected upload must not block the account. The
   * name is already saved at this point; the user lands on the app either way and
   * can retry from the account page.
   */
  private uploadThenFinish(): void {
    if (!this.pending) {
      this.finish();
      return;
    }
    this.auth.uploadAvatar(this.pending).subscribe({
      next: () => this.finish(),
      error: (err) => {
        this.saving.set(false);
        this.pending = null;
        this.avatarError.set(
          err?.error?.detail || 'Your name was saved, but the image could not be uploaded.',
        );
      },
    });
  }

  private finish(): void {
    this.saving.set(false);
    this.router.navigateByUrl('/overview');
  }

  private revokePreview(): void {
    const url = this.previewUrl();
    if (url) URL.revokeObjectURL(url);
  }
}
