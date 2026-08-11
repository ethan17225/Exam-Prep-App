import { Injectable, computed, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

export interface AuthUser {
  id: string;
  email: string;
  role: 'student' | 'instructor';
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

  register(email: string, password: string, inviteCode: string): Observable<AuthResponse> {
    return this.http
      .post<AuthResponse>(`${this.base}/register`, { email, password, invite_code: inviteCode })
      .pipe(tap((res) => this.store(res)));
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
    this.user.set(res.user);
    localStorage.setItem(TOKEN_KEY, res.token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
  }
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
