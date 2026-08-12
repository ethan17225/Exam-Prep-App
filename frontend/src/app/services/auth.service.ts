import { Injectable, computed, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

export type UserRole = 'student' | 'instructor';

export interface AuthUser {
  id: string;
  email: string;
  role: UserRole;
  /** The preferred name. Null until onboarding sets it — that is the gate. */
  display_name: string | null;
  avatar: string | null;
  /** An instructor's own enrolment code. Always null for a student. */
  invite_code: string | null;
}

/** `GET /api/auth/me` — AuthUser plus the one field that is not a column. */
export interface CurrentUser extends AuthUser {
  instructor_name: string | null;
}

interface AuthResponse {
  token: string;
  user: AuthUser;
}

const TOKEN_KEY = 'exam_token';
const USER_KEY = 'exam_user';
/** Prefix of the per-attempt autosave mirror written by take-exam. */
export const PROGRESS_KEY_PREFIX = 'exam_progress_';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private base = '/api/auth';

  private token = signal<string | null>(null);
  user = signal<AuthUser | null>(null);
  isLoggedIn = computed(() => this.user() !== null);
  isInstructor = computed(() => this.user()?.role === 'instructor');

  /**
   * A signed-in account that has not chosen a preferred name yet. `onboardingGuard`
   * reads this, so it must stay false when nobody is signed in — otherwise the
   * login page itself would redirect.
   */
  needsOnboarding = computed(() => {
    const user = this.user();
    return user !== null && !user.display_name;
  });

  /** Fallback for the nav when there is no avatar. */
  initials = computed(() => initialsOf(this.user()));

  constructor(private http: HttpClient) {
    const stored = localStorage.getItem(TOKEN_KEY);
    // Drop an already-expired token at bootstrap, otherwise the first page load
    // fires half a dozen requests that all 401 before the redirect lands.
    if (stored && !isExpired(stored)) {
      this.token.set(stored);
      const rawUser = localStorage.getItem(USER_KEY);
      if (rawUser) {
        try {
          this.user.set(JSON.parse(rawUser) as AuthUser);
        } catch {
          this.clear();
        }
      }
    } else if (stored) {
      this.clear();
    }
  }

  getToken(): string | null {
    return this.token();
  }

  login(email: string, password: string): Observable<AuthResponse> {
    return this.http
      .post<AuthResponse>(`${this.base}/login`, { email, password })
      .pipe(tap((res) => this.store(res)));
  }

  register(
    email: string,
    password: string,
    inviteCode: string,
    role: UserRole,
  ): Observable<AuthResponse> {
    return this.http
      .post<AuthResponse>(`${this.base}/register`, {
        email,
        password,
        invite_code: inviteCode,
        role,
      })
      .pipe(tap((res) => this.store(res)));
  }

  /**
   * Changing the password revokes every token for the account, including the one
   * this request was made with — so the fresh one in the response must be stored
   * or the next request 401s and bounces the user to /login.
   */
  changePassword(currentPassword: string, newPassword: string): Observable<AuthResponse> {
    return this.http
      .post<AuthResponse>(`${this.base}/password`, {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .pipe(tap((res) => this.store(res)));
  }

  /** Re-reads the profile and refreshes the cached copy the nav renders from. */
  refreshMe(): Observable<CurrentUser> {
    return this.http.get<CurrentUser>(`${this.base}/me`).pipe(tap((me) => this.storeUser(me)));
  }

  /** Sets the preferred name. This is what completes onboarding. */
  updateProfile(displayName: string): Observable<CurrentUser> {
    return this.http
      .patch<CurrentUser>(`${this.base}/me`, { display_name: displayName })
      .pipe(tap((me) => this.storeUser(me)));
  }

  uploadAvatar(file: File): Observable<{ avatar: string }> {
    const form = new FormData();
    form.append('file', file);
    return this.http
      .post<{ avatar: string }>(`${this.base}/me/avatar`, form)
      .pipe(tap((res) => this.patchUser({ avatar: res.avatar })));
  }

  removeAvatar(): Observable<{ avatar: null }> {
    return this.http
      .delete<{ avatar: null }>(`${this.base}/me/avatar`)
      .pipe(tap(() => this.patchUser({ avatar: null })));
  }

  logout(): void {
    // Fire-and-forget: it only clears the cookie used by <img>/<a> requests.
    this.http.post(`${this.base}/logout`, {}).subscribe({ error: () => {} });
    this.clear();
  }

  /** Clears local credentials without a server call — used by the 401 interceptor. */
  clear(): void {
    this.token.set(null);
    this.user.set(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);

    // Also drop every autosave mirror. On a shared machine these otherwise
    // outlive the session, and the next signed-in user resuming the same exam
    // would restore the previous user's answers into their own attempt.
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(PROGRESS_KEY_PREFIX)) localStorage.removeItem(key);
    }
  }

  private store(res: AuthResponse): void {
    this.token.set(res.token);
    localStorage.setItem(TOKEN_KEY, res.token);
    this.storeUser(res.user);
  }

  private storeUser(user: AuthUser): void {
    this.user.set(user);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  /** Copy-on-write, so the nav's computed signals recompute. */
  private patchUser(patch: Partial<AuthUser>): void {
    const current = this.user();
    if (current) this.storeUser({ ...current, ...patch });
  }
}

/** Up to two letters from the preferred name, falling back to the email. */
export function initialsOf(user: Pick<AuthUser, 'display_name' | 'email'> | null): string {
  if (!user) return '';
  const source = user.display_name?.trim() || user.email;
  const words = source.split(/[\s._-]+/).filter(Boolean);
  if (words.length === 0) return '';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

/** Reads `exp` out of a JWT payload. Treats anything unparseable as expired. */
function isExpired(token: string): boolean {
  try {
    // JWT payloads are base64url, so restore the standard alphabet before atob —
    // otherwise a '-' or '_' in the payload throws and a valid token is treated
    // as expired, intermittently bouncing the user to /login.
    const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(b64));
    return typeof payload.exp !== 'number' || payload.exp * 1000 <= Date.now();
  } catch {
    return true;
  }
}
