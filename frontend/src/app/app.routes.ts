import { Routes } from '@angular/router';

import {
  authGuard,
  instructorGuard,
  instructorMatch,
  onboardingGuard,
  studentMatch,
} from './services/auth.guard';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./pages/login/login').then((m) => m.LoginPage) },
  {
    path: 'register',
    loadComponent: () => import('./pages/register/register').then((m) => m.RegisterPage),
  },

  // Everything below requires a session. canActivateChild runs the guards on every
  // child navigation, so a new page cannot be reached with a cleared token — or
  // before the account has a preferred name.
  {
    path: '',
    canActivateChild: [authGuard, onboardingGuard],
    children: [
      { path: '', redirectTo: 'overview', pathMatch: 'full' },
      {
        path: 'onboarding',
        loadComponent: () => import('./pages/onboarding/onboarding').then((m) => m.OnboardingPage),
      },
      {
        path: 'account',
        loadComponent: () => import('./pages/account/account').then((m) => m.AccountPage),
      },
      // Two entirely different landing pages behind one URL. canMatch falls
      // through to the next candidate instead of redirecting, so each role loads
      // only its own bundle. The student route is last and unguarded, which makes
      // it the fallback if neither matcher runs.
      {
        path: 'overview',
        canMatch: [instructorMatch],
        loadComponent: () =>
          import('./pages/instructor-overview/instructor-overview').then(
            (m) => m.InstructorOverviewPage,
          ),
      },
      {
        path: 'overview',
        canMatch: [studentMatch],
        loadComponent: () => import('./pages/overview/overview').then((m) => m.OverviewPage),
      },
      {
        path: 'students',
        canActivate: [instructorGuard],
        loadComponent: () => import('./pages/students/students').then((m) => m.StudentsPage),
      },
      {
        path: 'upload',
        loadComponent: () => import('./pages/upload/upload').then((m) => m.UploadPage),
      },
      {
        path: 'exams',
        loadComponent: () => import('./pages/exams/exams').then((m) => m.ExamsPage),
      },
      {
        path: 'exams/:id/edit',
        loadComponent: () => import('./pages/edit-exam/edit-exam').then((m) => m.EditExamPage),
      },
      {
        path: 'in-progress',
        loadComponent: () =>
          import('./pages/in-progress/in-progress').then((m) => m.InProgressPage),
      },
      {
        path: 'exam/:id',
        loadComponent: () => import('./pages/take-exam/take-exam').then((m) => m.TakeExamPage),
      },
      {
        path: 'flashcards/:id',
        loadComponent: () => import('./pages/flashcards/flashcards').then((m) => m.FlashcardsPage),
      },
      {
        path: 'results/:id',
        loadComponent: () => import('./pages/results/results').then((m) => m.ResultsPage),
      },
      {
        path: 'history',
        loadComponent: () => import('./pages/history/history').then((m) => m.HistoryPage),
      },
      {
        path: 'history/:id',
        loadComponent: () =>
          import('./pages/history-detail/history-detail').then((m) => m.HistoryDetailPage),
      },
      {
        path: 'documents',
        loadComponent: () => import('./pages/documents/documents').then((m) => m.DocumentsPage),
      },
      {
        path: 'tracking',
        canActivate: [instructorGuard],
        loadComponent: () => import('./pages/tracking/tracking').then((m) => m.TrackingPage),
      },
      // The page was called Admin until the instructor nav was reorganized.
      // Kept so bookmarks and anything already linking to it still resolve.
      { path: 'admin', redirectTo: 'tracking', pathMatch: 'full' },
    ],
  },

  // Unknown URLs otherwise render an empty outlet (nginx serves index.html for any path).
  { path: '**', redirectTo: '' },
];
