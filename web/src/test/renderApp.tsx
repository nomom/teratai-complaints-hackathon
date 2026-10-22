import { QueryClient } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { AppProviders } from '@/app/providers/AppProviders';
import { routes } from '@/app/routes';
import { session } from '@/lib/session';

/** Mount the whole app at `path`, optionally already signed in (the fake API's tokens are "token-<username>"). */
export function renderApp(path: string, { as }: { as?: string } = {}) {
  if (as) session.set(`token-${as}`);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  const user = userEvent.setup();
  const view = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, router, user };
}
