import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';

import { Spinner } from '@/components/ui';
import { useAuth } from '@/features/auth/AuthProvider';

import { canOpen, homePath, type PageKey } from './navigation';

/** Nothing behind this shows until someone is signed in. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <Spinner label="Checking your session" />;
  if (status === 'signedOut') return <Navigate to="/sign-in" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

/** A page outside the role's list sends the user to their own first page (the API refuses the data anyway). */
export function RequirePage({ page, children }: { page: PageKey; children: ReactNode }) {
  const { user } = useAuth();
  if (!user) return null;
  if (!canOpen(user.role, page)) return <Navigate to={homePath(user.role)} replace />;
  return <>{children}</>;
}

export function RoleHome() {
  const { user } = useAuth();
  return user ? <Navigate to={homePath(user.role)} replace /> : null;
}
