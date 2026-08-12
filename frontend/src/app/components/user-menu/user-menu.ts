import { Component, HostListener, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../services/auth.service';

/**
 * The avatar button at the left of the nav, and the Account / Sign out popover it
 * opens. Signing out lives here rather than as its own tab so the nav has one
 * place for everything about the current account.
 */
@Component({
  selector: 'app-user-menu',
  imports: [RouterLink],
  templateUrl: './user-menu.html',
  styleUrl: './user-menu.scss',
})
export class UserMenuComponent {
  open = signal(false);

  constructor(
    public auth: AuthService,
    private router: Router,
  ) {}

  toggle(): void {
    this.open.update((value) => !value);
  }

  close(): void {
    this.open.set(false);
  }

  logout(): void {
    this.close();
    this.auth.logout();
    this.router.navigate(['/login']);
  }

  /**
   * Any click outside the component closes the popover. Bound on the document
   * rather than a backdrop element so the click still reaches whatever was
   * clicked — a backdrop would swallow the first tap on every nav link.
   */
  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.open()) return;
    const host = event.target as HTMLElement;
    if (!host.closest('app-user-menu')) this.close();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.close();
  }
}
