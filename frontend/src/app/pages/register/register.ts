import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-register',
  imports: [FormsModule, RouterLink],
  templateUrl: './register.html',
})
export class RegisterPage implements OnInit {
  email = signal('');
  password = signal('');
  inviteCode = signal('');
  loading = signal(false);
  error = signal('');

  constructor(
    private auth: AuthService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    if (this.auth.isLoggedIn()) {
      this.router.navigateByUrl('/overview');
    }
  }

  submit(): void {
    const email = this.email().trim();
    const password = this.password();
    const invite = this.inviteCode().trim();

    if (!email || !password || !invite) {
      this.error.set('All fields are required.');
      return;
    }
    if (password.length < 8) {
      this.error.set('Password must be at least 8 characters.');
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.auth.register(email, password, invite).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigateByUrl('/overview');
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || 'Registration failed.');
      },
    });
  }
}
