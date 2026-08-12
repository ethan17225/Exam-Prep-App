import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService, UserRole } from '../../services/auth.service';

@Component({
  selector: 'app-register',
  imports: [FormsModule, RouterLink],
  templateUrl: './register.html',
  styleUrl: './register.scss',
})
export class RegisterPage implements OnInit {
  email = signal('');
  password = signal('');
  inviteCode = signal('');
  role = signal<UserRole>('student');
  loading = signal(false);
  error = signal('');

  /** The two roles take entirely different codes, so the label has to say which. */
  inviteHint = computed(() =>
    this.role() === 'instructor'
      ? 'The instructor sign-up code for this deployment.'
      : "Your instructor's personal code — it also enrols you with them.",
  );

  constructor(
    private auth: AuthService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    if (this.auth.isLoggedIn()) {
      this.router.navigateByUrl('/overview');
    }
  }

  setRole(role: UserRole): void {
    this.role.set(role);
    // The old code is meaningless for the other role, and leaving it in place
    // makes the resulting 403 look like a server problem.
    this.inviteCode.set('');
    this.error.set('');
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
    this.auth.register(email, password, invite, this.role()).subscribe({
      next: () => {
        this.loading.set(false);
        // The account exists but has no preferred name yet, which is what
        // /onboarding collects. Going to /overview would bounce straight back.
        this.router.navigateByUrl('/onboarding');
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || 'Registration failed.');
      },
    });
  }
}
