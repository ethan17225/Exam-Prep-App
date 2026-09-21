import { Routes } from '@angular/router';

import {
  adminGuard,
  adminMatch,
  authGuard,
  classroomGuard,
  instructorGuard,
  instructorMatch,
  onboardingGuard,
  studentGuard,
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
      // Three entirely different landing pages behind one URL. canMatch falls
      // through to the next candidate instead of redirecting, so each role loads
      // only its own bundle. Each matcher is exact, so declaration order is
      // only a readability choice.
      {
        path: 'overview',
        canMatch: [adminMatch],
        loadComponent: () =>
          import('./pages/admin-overview/admin-overview').then((m) => m.AdminOverviewPage),
      },
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
        canActivate: [classroomGuard],
        loadComponent: () => import('./pages/upload/upload').then((m) => m.UploadPage),
      },
      {
        path: 'exams',
        canActivate: [classroomGuard],
        loadComponent: () => import('./pages/exams/exams').then((m) => m.ExamsPage),
      },
      {
        path: 'exams/:id/edit',
        canActivate: [classroomGuard],
        loadComponent: () => import('./pages/edit-exam/edit-exam').then((m) => m.EditExamPage),
      },
      {
        path: 'in-progress',
        canActivate: [studentGuard],
        loadComponent: () =>
          import('./pages/in-progress/in-progress').then((m) => m.InProgressPage),
      },
      {
        path: 'exam/:id',
        canActivate: [studentGuard],
        loadComponent: () => import('./pages/take-exam/take-exam').then((m) => m.TakeExamPage),
      },
      {
        path: 'flashcards/:id',
        canActivate: [classroomGuard],
        loadComponent: () => import('./pages/flashcards/flashcards').then((m) => m.FlashcardsPage),
      },
      {
        path: 'results/:id',
        canActivate: [studentGuard],
        loadComponent: () => import('./pages/results/results').then((m) => m.ResultsPage),
      },
      {
        path: 'history',
        canActivate: [studentGuard],
        loadComponent: () => import('./pages/history/history').then((m) => m.HistoryPage),
      },
      {
        path: 'history/:id',
        canActivate: [studentGuard],
        loadComponent: () =>
          import('./pages/history-detail/history-detail').then((m) => m.HistoryDetailPage),
      },
      {
        path: 'documents',
        canActivate: [classroomGuard],
        loadComponent: () => import('./pages/documents/documents').then((m) => m.DocumentsPage),
      },
      {
        path: 'tracking',
        canActivate: [instructorGuard],
        loadComponent: () => import('./pages/tracking/tracking').then((m) => m.TrackingPage),
      },
      // ── Platform administration ──
      //
      // /admin belonged to the instructor tracking page until this role existed,
      // and some bookmarks still point at it. Rather than break those, the same
      // canMatch fall-through used by /overview sends an admin to their console
      // and everyone else to the page they were expecting.
      { path: 'admin', canMatch: [adminMatch], redirectTo: 'admin/users', pathMatch: 'full' },
      { path: 'admin', redirectTo: 'tracking', pathMatch: 'full' },
      {
        path: 'admin/users',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./pages/admin-users/admin-users').then((m) => m.AdminUsersPage),
      },
      {
        path: 'admin/content',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./pages/admin-content/admin-content').then((m) => m.AdminContentPage),
      },
      {
        path: 'admin/audit',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./pages/admin-audit/admin-audit').then((m) => m.AdminAuditPage),
      },
      {
        path: 'admin/system',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./pages/admin-system/admin-system').then((m) => m.AdminSystemPage),
      },
    ],
  },

  // Unknown URLs otherwise render an empty outlet (nginx serves index.html for any path).
  { path: '**', redirectTo: '' },
];
