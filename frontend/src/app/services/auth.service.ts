import { Injectable, computed, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, switchMap, tap } from 'rxjs';

/** Three distinct roles. Admin is neither a teacher nor a student. */
export type UserRole = 'student' | 'instructor' | 'admin';

export interface AuthUser {
  id: string;
  email: string;
  role: UserRole;
  /** The preferred name. Null until onboarding sets it — that is the gate. */
  display_name: string | null;
  avatar: string | null;
  /** An instructor's own enrolment code. Null for a student or an admin. */
  invite_code: string | null;
  /** Present when the bearer is an impersonation session (from GET /me). */
  impersonating?: boolean;
  impersonated_by?: Impersonator | null;
}

export interface Impersonator {
  id: string;
  email: string;
}

/** `GET /api/auth/me` — AuthUser plus the one field that is not a column. */
export interface CurrentUser extends AuthUser {
  instructor_name: string | null;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

const TOKEN_KEY = 'exam_token';
const USER_KEY = 'exam_user';
/** sessionStorage: admin credentials while acting as another user. */
const IMPERSONATION_BACKUP_TOKEN_KEY = 'exam_impersonation_backup_token';
const IMPERSONATION_BACKUP_USER_KEY = 'exam_impersonation_backup_user';
/** Prefix of the per-attempt autosave mirror written by take-exam. */
export const PROGRESS_KEY_PREFIX = 'exam_progress_v2_';
const LEGACY_PROGRESS_KEY_PREFIX = 'exam_progress_';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private base = '/api/auth';
  private platformBase = '/api/platform';

  private token = signal<string | null>(null);
  user = signal<AuthUser | null>(null);
  isLoggedIn = computed(() => this.user() !== null);
  isStudent = computed(() => this.user()?.role === 'student');
  isInstructor = computed(() => this.user()?.role === 'instructor');
  isAdmin = computed(() => this.user()?.role === 'admin');

  /**
   * True when the active bearer is an impersonation JWT. Driven by /me flags
   * when available, otherwise by the JWT `act` claim so a refresh mid-session
   * still shows the banner before refreshMe returns.
   */
  isImpersonating = computed(() => {
    const user = this.user();
    if (user?.impersonating) return true;
    const token = this.token();
    return token !== null && hasActClaim(token);
  });

  endingImpersonation = signal(false);

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

  constructor(
    private http: HttpClient,
    private router: Router,
  ) {
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

  /**
   * Start a full act-as session as `userId`. Stashes the admin token in
   * sessionStorage so Exit can restore without a second login.
   */
  startImpersonation(userId: string): Observable<CurrentUser> {
    this.backupAdminSession();
    return this.http
      .post<AuthResponse>(`${this.platformBase}/users/${userId}/impersonate`, {})
      .pipe(
        tap((res) => this.store(res)),
        switchMap(() => this.refreshMe()),
        tap(() => void this.router.navigateByUrl('/overview')),
      );
  }

  /** End impersonation: fresh admin token from the server, then restore admin UI. */
  endImpersonation(): Observable<AuthResponse> {
    this.endingImpersonation.set(true);
    return this.http.post<AuthResponse>(`${this.platformBase}/impersonate/end`, {}).pipe(
      tap({
        next: (res) => {
          this.clearImpersonationBackup();
          this.store(res);
          this.endingImpersonation.set(false);
          void this.router.navigateByUrl('/admin/users');
        },
        error: () => {
          this.endingImpersonation.set(false);
        },
      }),
    );
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
    this.clearImpersonationBackup();

    // Also drop every autosave mirror. On a shared machine these otherwise
    // outlive the session, and the next signed-in user resuming the same exam
    // would restore the previous user's answers into their own attempt.
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(LEGACY_PROGRESS_KEY_PREFIX)) localStorage.removeItem(key);
    }
  }

  private backupAdminSession(): void {
    const token = this.token();
    const user = this.user();
    if (token) sessionStorage.setItem(IMPERSONATION_BACKUP_TOKEN_KEY, token);
    if (user) sessionStorage.setItem(IMPERSONATION_BACKUP_USER_KEY, JSON.stringify(user));
  }

  private clearImpersonationBackup(): void {
    sessionStorage.removeItem(IMPERSONATION_BACKUP_TOKEN_KEY);
    sessionStorage.removeItem(IMPERSONATION_BACKUP_USER_KEY);
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
    const payload = decodeJwtPayload(token);
    const exp = payload['exp'];
    return typeof exp !== 'number' || exp * 1000 <= Date.now();
  } catch {
    return true;
  }
}

function hasActClaim(token: string): boolean {
  try {
    const payload = decodeJwtPayload(token);
    const act = payload['act'];
    return typeof act === 'string' && act.length > 0;
  } catch {
    return false;
  }
}

function decodeJwtPayload(token: string): Record<string, unknown> {
  // JWT payloads are base64url, so restore the standard alphabet before atob —
  // otherwise a '-' or '_' in the payload throws and a valid token is treated
  // as expired, intermittently bouncing the user to /login.
  const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
  return JSON.parse(atob(b64)) as Record<string, unknown>;
}
