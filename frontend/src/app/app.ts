import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';

import { UserMenuComponent } from './components/user-menu/user-menu';
import { AuthService } from './services/auth.service';
import { httpErrorDetail } from './services/exam.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, UserMenuComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  constructor(public auth: AuthService) {}

  exitImpersonation(): void {
    this.auth.endImpersonation().subscribe({
      error: (err) => {
        alert(httpErrorDetail(err) || 'Could not end impersonation.');
      },
    });
  }
}
