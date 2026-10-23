import { screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { QUEUE_REFRESH_MS } from '@/features/cases/hooks';
import { installFakeApi } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

const openCase = () => screen.findByRole('article', { name: /^Case / });

describe('approval queue', () => {
  afterEach(() => vi.useRealTimers());

  it('lists every case, the highest priority first, with that case opened below', async () => {
    installFakeApi();
    renderApp('/approval', { as: 'officer1' });
    expect(await screen.findByRole('heading', { name: 'Approval queue (2)' })).toBeInTheDocument();
    const rows = within(screen.getByRole('table', { name: /most urgent first/ })).getAllByRole('row').slice(1);
    // CMP-P3 is the more recently updated case; priority still wins
    expect(rows.map((r) => within(r).getAllByRole('cell')[1].textContent)).toEqual(['CMP-P1', 'CMP-P3']);
    expect(await openCase()).toHaveAccessibleName('Case CMP-P1');
    expect(rows[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('shows a complaint that arrives through the API without anyone clicking', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = installFakeApi();
    renderApp('/approval', { as: 'officer1' });
    expect(await screen.findByRole('heading', { name: 'Approval queue (2)' })).toBeInTheDocument();
    // the live round posts straight to the API; the worker stores the decided case
    api.cases.push({ ...structuredClone(api.cases.find((c) => c.complaint_id === 'CMP-P3')!), complaint_id: 'LIVE-NEW' });
    await vi.advanceTimersByTimeAsync(QUEUE_REFRESH_MS + 100);
    expect(await screen.findByRole('cell', { name: 'LIVE-NEW' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Approval queue (3)' })).toBeInTheDocument();
  });

  it('opens another case when its row is selected', async () => {
    installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await user.click(await screen.findByRole('cell', { name: 'CMP-P3' }));
    expect(await screen.findByRole('article', { name: 'Case CMP-P3' })).toBeInTheDocument();
  });

  it('shows the summary first and the details in four tabs', async () => {
    installFakeApi();
    renderApp('/approval', { as: 'officer1' });
    await openCase();
    expect(await screen.findByText('CMP-P1 headline')).toBeInTheDocument();
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(
      ["Customer's message", 'Full evidence', 'How the agent decided', 'Audit log']);
  });

  it('approves and confirms', async () => {
    const api = installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await openCase();
    await user.click(await screen.findByRole('button', { name: 'Approve and send' }));
    // the approved case leaves the queue and the next one opens; the confirmation must survive that
    expect(await screen.findByRole('article', { name: 'Case CMP-P3' })).toBeInTheDocument();
    expect(screen.getByText('CMP-P1 approved and the reply was sent.')).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === '/cases/CMP-P1/approve')?.body).toEqual({ reply_text: null });
  });

  it('refuses an edited reply that fails the self-check and lists the problems', async () => {
    const api = installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await openCase();
    await user.type(await screen.findByLabelText(/Reply to the customer/), ' We refunded TXN-9999999.');
    await user.click(screen.getByRole('button', { name: 'Approve and send' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Not sent: the reply failed the self-check.');
    expect(screen.getByRole('alert')).toHaveTextContent('TXN-9999999');
    expect(api.cases.find((c) => c.complaint_id === 'CMP-P1')?.status).toBe('PENDING_APPROVAL');
  });

  it('rejects and confirms', async () => {
    installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await openCase();
    await user.click(await screen.findByRole('button', { name: 'Reject' }));
    expect(await screen.findByText('CMP-P1 rejected. No reply was sent.')).toBeInTheDocument();
  });
});

describe('other queues', () => {
  it('shows an empty state and no table for an empty queue', async () => {
    installFakeApi();
    renderApp('/awaiting', { as: 'manager1' });
    expect(await screen.findByText('Nothing in awaiting customer')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('lets the manager flag a resolved case for review', async () => {
    installFakeApi();
    const { user } = renderApp('/resolved', { as: 'manager1' });
    await openCase();
    await user.click(await screen.findByRole('button', { name: 'Flag for review' }));
    await user.type(await screen.findByLabelText('What looks wrong?'), 'wrong transaction refunded');
    await user.click(screen.getByRole('button', { name: 'Flag' }));
    expect(await screen.findByText('CMP-AUTO flagged for review.')).toBeInTheDocument();
    expect(await screen.findByText(/Flagged for review by manager1/)).toHaveTextContent('wrong transaction refunded');
  });

  it("shows a fraud analyst only the fraud route's cases", async () => {
    installFakeApi();
    renderApp('/cases', { as: 'fraud1' });
    expect(await screen.findByRole('heading', { name: 'All cases (1)' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'CMP-FRAUD' })).toBeInTheDocument();
  });
});
