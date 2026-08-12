import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';

import { UserMenuComponent } from './components/user-menu/user-menu';
import { AuthService } from './services/auth.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, UserMenuComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  // Signing out moved into the user menu, which is why this class has no logic
  // left beyond exposing auth to the template.
  constructor(public auth: AuthService) {}
}
