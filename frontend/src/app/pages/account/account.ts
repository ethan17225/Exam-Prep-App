import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthService, CurrentUser, initialsOf } from '../../services/auth.service';

@Component({
  selector: 'app-account',
  imports: [FormsModule],
  templateUrl: './account.html',
  styleUrl: './account.scss',
})
export class AccountPage implements OnInit {
  me = signal<CurrentUser | null>(null);
  loading = signal(true);
  loadError = signal('');

  // ── Preferred name ──
  nameDraft = signal('');
  savingName = signal(false);
  nameError = signal('');
  nameSaved = signal(false);

  // ── Avatar ──
  savingAvatar = signal(false);
  avatarError = signal('');

  // ── Password ──
  currentPassword = signal('');
  newPassword = signal('');
  confirmPassword = signal('');
  savingPassword = signal(false);
  passwordError = signal('');
  passwordSaved = signal(false);

  codeCopied = signal(false);

  constructor(public auth: AuthService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    // Read through rather than rendering the cached copy: `instructor_name` is not
    // in the cached user, and a name changed on another device would be stale.
    this.auth.refreshMe().subscribe({
      next: (me) => {
        this.me.set(me);
        this.nameDraft.set(me.display_name ?? '');
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail || 'Could not load your account.');
      },
    });
  }

  initials(): string {
    return initialsOf(this.me());
  }

  saveName(): void {
    const name = this.nameDraft().trim();
    if (!name) {
      this.nameError.set('Preferred name cannot be empty.');
      return;
    }
    this.savingName.set(true);
    this.nameError.set('');
    this.nameSaved.set(false);
    this.auth.updateProfile(name).subscribe({
      next: (me) => {
        this.savingName.set(false);
        this.me.set(me);
        this.nameSaved.set(true);
      },
      error: (err) => {
        this.savingName.set(false);
        this.nameError.set(err?.error?.detail || 'Could not save your name.');
      },
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    // Reset the input so picking the same file twice after a failure still fires.
    input.value = '';

    this.savingAvatar.set(true);
    this.avatarError.set('');
    this.auth.uploadAvatar(file).subscribe({
      next: (res) => {
        this.savingAvatar.set(false);
        this.patchMe({ avatar: res.avatar });
      },
      error: (err) => {
        this.savingAvatar.set(false);
        this.avatarError.set(err?.error?.detail || 'Could not upload that image.');
      },
    });
  }

  removeAvatar(): void {
    this.savingAvatar.set(true);
    this.avatarError.set('');
    this.auth.removeAvatar().subscribe({
      next: () => {
        this.savingAvatar.set(false);
        this.patchMe({ avatar: null });
      },
      error: (err) => {
        this.savingAvatar.set(false);
        this.avatarError.set(err?.error?.detail || 'Could not remove your image.');
      },
    });
  }

  changePassword(): void {
    const current = this.currentPassword();
    const next = this.newPassword();

    this.passwordSaved.set(false);
    if (!current || !next) {
      this.passwordError.set('Both passwords are required.');
      return;
    }
    if (next.length < 8) {
      this.passwordError.set('New password must be at least 8 characters.');
      return;
    }
    if (next !== this.confirmPassword()) {
      this.passwordError.set('The new passwords do not match.');
      return;
    }

    this.savingPassword.set(true);
    this.passwordError.set('');
    // AuthService stores the fresh token from the response — the change revoked
    // the one this request was sent with, including on every other device.
    this.auth.changePassword(current, next).subscribe({
      next: () => {
        this.savingPassword.set(false);
        this.passwordSaved.set(true);
        this.currentPassword.set('');
        this.newPassword.set('');
        this.confirmPassword.set('');
      },
      error: (err) => {
        this.savingPassword.set(false);
        this.passwordError.set(err?.error?.detail || 'Could not change your password.');
      },
    });
  }

  copyInviteCode(): void {
    const code = this.me()?.invite_code;
    if (!code) return;
    navigator.clipboard.writeText(code).then(() => {
      this.codeCopied.set(true);
      setTimeout(() => this.codeCopied.set(false), 2000);
    });
  }

  private patchMe(patch: Partial<CurrentUser>): void {
    const current = this.me();
    if (current) this.me.set({ ...current, ...patch });
  }
}
