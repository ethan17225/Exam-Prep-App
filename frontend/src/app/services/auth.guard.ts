import { inject } from '@angular/core';
import { CanActivateFn, CanMatchFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isLoggedIn()) return true;
  return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};

/** Instructor-only routes. Students are sent to the overview, not to login. */
export const instructorGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isLoggedIn()) {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
  return auth.isInstructor() ? true : router.createUrlTree(['/overview']);
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
 * Route-level role split for /overview: students and instructors get entirely
 * different landing pages. `canMatch` rather than `canActivate` because it runs in
 * an injection context and skips to the next matching route instead of
 * redirecting, which keeps both page bundles lazy.
 */
export const studentMatch: CanMatchFn = () => !inject(AuthService).isInstructor();

export const instructorMatch: CanMatchFn = () => inject(AuthService).isInstructor();
