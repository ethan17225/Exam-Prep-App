import { inject } from '@angular/core';
import { CanActivateFn, CanMatchFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isLoggedIn()) return true;
  return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};

/**
 * Teaching routes. Exact role: an admin is not an instructor, so they land on
 * their own overview rather than an empty class page. Students are sent there
 * too, not to login.
 */
export const instructorGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isLoggedIn()) {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
  return auth.isInstructor() ? true : router.createUrlTree(['/overview']);
};

/**
 * Student exam-taking routes. Instructors and admins have no attempts of their
 * own, so these pages are empty for them.
 */
export const studentGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isLoggedIn()) {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
  return auth.isStudent() ? true : router.createUrlTree(['/overview']);
};

/**
 * Shared classroom pages (exams, upload, documents). Students and instructors
 * both use them; an admin oversees the same material from /admin/content.
 */
export const classroomGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isLoggedIn()) {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
  return auth.isStudent() || auth.isInstructor() ? true : router.createUrlTree(['/overview']);
};

/**
 * Platform administration. Exact role, unlike `instructorGuard`: these pages can
 * change anyone's role or delete their work, and the server gates them the same
 * way. Anyone else is sent to their own overview rather than to login.
 */
export const adminGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isLoggedIn()) {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
  return auth.isAdmin() ? true : router.createUrlTree(['/overview']);
};

/**
 * Holds a freshly registered account on /onboarding until it has a preferred name.
 * Runs alongside `authGuard` on the guarded parent, so it must let /onboarding
 * itself through or the redirect loops forever.
 */
export const onboardingGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (state.url.startsWith(ONBOARDING_PATH)) return true;
  return auth.needsOnboarding() ? router.createUrlTree([ONBOARDING_PATH]) : true;
};

const ONBOARDING_PATH = '/onboarding';

/**
 * Route-level role split for /overview: students, instructors and admins get
 * entirely different landing pages. `canMatch` rather than `canActivate` because
 * it runs in an injection context and skips to the next matching route instead of
 * redirecting, which keeps all three page bundles lazy.
 */
export const studentMatch: CanMatchFn = () => inject(AuthService).isStudent();

export const instructorMatch: CanMatchFn = () => inject(AuthService).isInstructor();

export const adminMatch: CanMatchFn = () => inject(AuthService).isAdmin();
