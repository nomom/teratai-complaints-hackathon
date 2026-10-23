import { useQuery } from '@tanstack/react-query';

import * as customerApi from './api';

export const meKeys = {
  profile: ['me', 'profile'] as const,
  statement: ['me', 'transactions'] as const,
};

// The bank's records don't change while the app runs: one fetch per sign-in (signing out clears the cache)
export const useProfile = () => useQuery({ queryKey: meKeys.profile, queryFn: customerApi.getProfile, staleTime: Infinity });

export const useStatement = () =>
  useQuery({ queryKey: meKeys.statement, queryFn: customerApi.getStatement, staleTime: Infinity });
