import { Suspense, type ReactNode } from 'react';
import type { RouteObject } from 'react-router';

import { Spinner } from '@/components/ui';
import { SignInPage } from '@/features/auth/pages/SignInPage';
import { QUEUES } from '@/features/cases/lib/queues';

import { RequireAuth, RequirePage, RoleHome } from './guards';
import { AppShell } from './layout/AppShell';
import {
  AllCasesPage,
  MyCasesPage,
  NewComplaintPage,
  ProfilePage,
  QueuePage,
  SubmitComplaintPage,
  TransactionsPage,
} from './lazyPages';
import { PAGE_DEFS, type PageKey } from './navigation';

const page = (key: PageKey, element: ReactNode): RouteObject => ({
  path: PAGE_DEFS[key].path.slice(1),
  element: (
    <RequirePage page={key}>
      <Suspense fallback={<Spinner label="Loading the page" />}>{element}</Suspense>
    </RequirePage>
  ),
});

/** Exported on its own so tests can mount it in a memory router. */
export const routes: RouteObject[] = [
  { path: '/sign-in', element: <SignInPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <RoleHome /> },
      page('approval', <QueuePage key="approval" config={QUEUES.approval} />),
      page('fraud', <QueuePage key="fraud" config={QUEUES.fraud} />),
      page('awaiting', <QueuePage key="awaiting" config={QUEUES.awaiting} />),
      page('resolved', <QueuePage key="resolved" config={QUEUES.resolved} />),
      page('cases', <AllCasesPage />),
      page('intake', <SubmitComplaintPage />),
      page('myCases', <MyCasesPage />),
      page('newComplaint', <NewComplaintPage />),
      page('profile', <ProfilePage />),
      page('transactions', <TransactionsPage />),
      { path: '*', element: <RoleHome /> },
    ],
  },
];
