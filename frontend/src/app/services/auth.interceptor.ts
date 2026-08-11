import { inject } from '@angular/core';
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthService } from './auth.service';

/**
 * Attaches the bearer token and handles 401 centrally.
 *
 * Central handling is what covers the many `.subscribe(fn)` call sites that have
 * no error callback — without it a 401 leaves those pages silently blank.
 * Note it rethrows rather than returning EMPTY: completing the observable would
 * leave every loading spinner running forever.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const token = auth.getToken();
  const authed = token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  return next(authed).pipe(
    catchError((err: HttpErrorResponse) => {
      // Login/register failures are the caller's to display, not a session expiry.
      const isAuthCall = req.url.includes('/api/auth/');
      if (err.status === 401 && !isAuthCall) {
        auth.clear();
        router.navigate(['/login'], { queryParams: { returnUrl: router.url } });
      }
      return throwError(() => err);
    }),
  );
};
