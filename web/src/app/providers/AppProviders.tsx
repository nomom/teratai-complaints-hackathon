import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { AuthProvider } from '@/features/auth/AuthProvider';
import { ApiError } from '@/lib/apiClient';

import { FlashProvider } from './FlashProvider';
import { ThemeProvider } from './ThemeProvider';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10000,
        refetchOnWindowFocus: true,
        // A refusal (4xx) won't change on retry; a dropped connection might
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      },
    },
  });
}

export function AppProviders({ children, queryClient }: { children: ReactNode; queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient());
  return (
    <ThemeProvider>
      <QueryClientProvider client={client}>
        <FlashProvider>
          <AuthProvider>{children}</AuthProvider>
        </FlashProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
