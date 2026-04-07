import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'overview', pathMatch: 'full' },
  { path: 'overview', loadComponent: () => import('./pages/overview/overview').then(m => m.OverviewPage) },
  { path: 'upload', loadComponent: () => import('./pages/upload/upload').then(m => m.UploadPage) },
  { path: 'exams', loadComponent: () => import('./pages/exams/exams').then(m => m.ExamsPage) },
  { path: 'exam/:id', loadComponent: () => import('./pages/take-exam/take-exam').then(m => m.TakeExamPage) },
  { path: 'results/:id', loadComponent: () => import('./pages/results/results').then(m => m.ResultsPage) },
  { path: 'history', loadComponent: () => import('./pages/history/history').then(m => m.HistoryPage) },
  { path: 'history/:id', loadComponent: () => import('./pages/history-detail/history-detail').then(m => m.HistoryDetailPage) },
];
