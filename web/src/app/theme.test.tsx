import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

describe('theme', () => {
  it('opens dark, switches to light, and keeps light after logging out', async () => {
    installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await screen.findByRole('heading', { name: 'Approval queue (2)' });
    expect(document.documentElement.dataset.theme).toBe('dark');

    await user.click(screen.getAllByRole('switch', { name: 'Dark mode' })[0]);
    expect(document.documentElement.dataset.theme).toBe('light');

    await user.click(screen.getByRole('button', { name: /account menu/ }));
    await user.click(await screen.findByRole('button', { name: 'Log out' }));
    expect(await screen.findByRole('heading', { name: 'Complaints Ops' })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(screen.getByRole('switch', { name: 'Dark mode' })).not.toBeChecked();
  });
});
