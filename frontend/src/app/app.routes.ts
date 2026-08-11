import { Routes } from '@angular/router';

import { authGuard, instructorGuard } from './services/auth.guard';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./pages/login/login').then(m => m.LoginPage) },
  { path: 'register', loadComponent: () => import('./pages/register/register').then(m => m.RegisterPage) },

  // Everything below requires a session. canActivateChild runs the guard on every
  // child navigation, so a new page cannot be reached with a cleared token.
  {
    path: '',
    canActivateChild: [authGuard],
    children: [
      { path: '', redirectTo: 'overview', pathMatch: 'full' },
      { path: 'overview', loadComponent: () => import('./pages/overview/overview').then(m => m.OverviewPage) },
      { path: 'upload', loadComponent: () => import('./pages/upload/upload').then(m => m.UploadPage) },
      { path: 'exams', loadComponent: () => import('./pages/exams/exams').then(m => m.ExamsPage) },
      { path: 'exams/:id/edit', loadComponent: () => import('./pages/edit-exam/edit-exam').then(m => m.EditExamPage) },
      { path: 'in-progress', loadComponent: () => import('./pages/in-progress/in-progress').then(m => m.InProgressPage) },
      { path: 'exam/:id', loadComponent: () => import('./pages/take-exam/take-exam').then(m => m.TakeExamPage) },
      { path: 'flashcards/:id', loadComponent: () => import('./pages/flashcards/flashcards').then(m => m.FlashcardsPage) },
      { path: 'results/:id', loadComponent: () => import('./pages/results/results').then(m => m.ResultsPage) },
      { path: 'history', loadComponent: () => import('./pages/history/history').then(m => m.HistoryPage) },
      { path: 'history/:id', loadComponent: () => import('./pages/history-detail/history-detail').then(m => m.HistoryDetailPage) },
      { path: 'documents', loadComponent: () => import('./pages/documents/documents').then(m => m.DocumentsPage) },
      { path: 'admin', canActivate: [instructorGuard], loadComponent: () => import('./pages/admin/admin').then(m => m.AdminPage) },
    ],
  },
];
