import { lazy } from 'react';

// Pages load on first visit, so staff never download the customer pages and the other way round

export const QueuePage = lazy(() => import('@/features/cases/pages/QueuePage').then((m) => ({ default: m.QueuePage })));

export const AllCasesPage = lazy(() =>
  import('@/features/cases/pages/AllCasesPage').then((m) => ({ default: m.AllCasesPage })));

export const SubmitComplaintPage = lazy(() =>
  import('@/features/cases/pages/SubmitComplaintPage').then((m) => ({ default: m.SubmitComplaintPage })));

export const MyCasesPage = lazy(() =>
  import('@/features/customer/pages/MyCasesPage').then((m) => ({ default: m.MyCasesPage })));

export const NewComplaintPage = lazy(() =>
  import('@/features/customer/pages/NewComplaintPage').then((m) => ({ default: m.NewComplaintPage })));
