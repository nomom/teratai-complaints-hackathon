import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

async function navLinks() {
  const nav = await screen.findByRole('navigation', { name: 'Pages' });
  return within(nav).getAllByRole('link').map((link) => link.textContent);
}

describe('pages per role', () => {
  it.each([
    ['officer1', ['Approval queue', 'Rejected', 'All cases', 'Dashboard', 'Submit complaint']],
    ['fraud1', ['Fraud queue', 'Rejected', 'All cases', 'Dashboard', 'Submit complaint']],
    ['manager1', ['Approval queue', 'Fraud queue', 'Awaiting customer', 'Rejected', 'Resolved automatically', 'All cases',
      'Audit log', 'Dashboard', 'Submit complaint']],
  ])('%s sees exactly its pages', async (username, pages) => {
    installFakeApi();
    renderApp('/', { as: username });
    expect(await navLinks()).toEqual(pages);
  });

  it('gives a customer only their own pages', async () => {
    const api = installFakeApi();
    api.signUp('CUS-00150', 'secret1');
    renderApp('/', { as: 'CUS-00150' });
    expect(await navLinks()).toEqual(['My cases', 'New complaint']);
  });

  it("sends a page outside the role back to the role's first page", async () => {
    installFakeApi();
    const { router } = renderApp('/fraud', { as: 'officer1' });
    expect(await screen.findByRole('heading', { name: 'Approval queue (2)' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/approval');
  });

  it("limits the sidebar counts to the role's cases", async () => {
    installFakeApi();
    renderApp('/', { as: 'officer1' });
    const counts = await screen.findByText('Cases you can see');
    const box = counts.parentElement!;
    expect(within(box).getByText('Approval queue')).toBeInTheDocument();
    expect(within(box).queryByText('Fraud queue')).not.toBeInTheDocument();
  });
});
