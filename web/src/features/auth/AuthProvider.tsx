import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { useFlash } from '@/app/providers/FlashProvider';
import { onUnauthorized } from '@/lib/apiClient';
import { session } from '@/lib/session';

import * as authApi from './api';
import type { User } from './types';

type Status = 'loading' | 'signedIn' | 'signedOut';

interface AuthContextValue {
  status: Status;
  user: User | null;
  signIn: (username: string, password: string) => Promise<User>;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { flash } = useFlash();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>(() => (session.get() ? 'loading' : 'signedOut'));

  const signOut = useCallback(() => {
    session.clear();
    setUser(null);
    setStatus('signedOut');
    queryClient.clear();                        // nothing from the last account stays in the cache
  }, [queryClient]);

  // A token from earlier in this tab: check it is still valid (expiry, removed account, changed role)
  useEffect(() => {
    if (!session.get()) return;
    let cancelled = false;
    authApi
      .me()
      .then((account) => {
        if (!cancelled) {
          setUser(account);
          setStatus('signedIn');
        }
      })
      .catch(() => {
        if (!cancelled) signOut();
      });
    return () => {
      cancelled = true;
    };
  }, [signOut]);

  // The API refused the session mid-use: sign out and say why
  useEffect(
    () =>
      onUnauthorized((error) => {
        signOut();
        flash('info', error.message);
      }),
    [signOut, flash],
  );

  const signIn = useCallback(async (username: string, password: string) => {
    const response = await authApi.login(username, password);
    session.set(response.access_token);
    setUser(response.user);
    setStatus('signedIn');
    return response.user;
  }, []);

  const value = useMemo(() => ({ status, user, signIn, signOut }), [status, user, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}

/** For pages behind the sign-in guard, where a user is always present. */
export function useUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error('useUser needs a signed-in user');
  return user;
}
