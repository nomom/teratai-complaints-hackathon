import { screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { QUEUE_REFRESH_MS } from '@/features/cases/hooks';
import { installFakeApi, makeCase } from '@/test/fakeApi';
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

  it('approves only after a review that names the refund', async () => {
    const api = installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await openCase();
    await user.click(await screen.findByRole('button', { name: 'Review and send' }));
    expect(api.calls.some((c) => c.path === '/cases/CMP-P1/approve')).toBe(false);      // nothing sent yet
    const review = screen.getByRole('region', { name: 'Check before you send' });
    expect(review).toHaveTextContent('CUS-02394');
    await user.click(within(review).getByRole('button', { name: 'Send RM 100.00 refund' }));
    // the approved case leaves the queue and the next one opens; the confirmation must survive that
    expect(await screen.findByRole('article', { name: 'Case CMP-P3' })).toBeInTheDocument();
    expect(screen.getByText('CMP-P1 approved: the RM 100.00 refund and the reply were sent.')).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === '/cases/CMP-P1/approve')?.body).toEqual({ reply_text: null, note: '' });
  });

  it('asks why an edited reply changed, and sends the reason', async () => {
    const api = installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await openCase();
    await user.type(await screen.findByLabelText(/Reply to the customer/), ' Thank you for waiting.');
    await user.click(screen.getByRole('button', { name: 'Review and send' }));
    const send = screen.getByRole('button', { name: 'Send RM 100.00 refund' });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText('Why did you change the reply? (required)'), 'warmer closing');
    await user.click(send);
    expect(await screen.findByRole('article', { name: 'Case CMP-P3' })).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === '/cases/CMP-P1/approve')?.body)
      .toEqual({ reply_text: 'Draft reply for CMP-P1 Thank you for waiting.', note: 'warmer closing' });
  });

  it('refuses an edited reply that fails the self-check and lists the problems', async () => {
    const api = installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await openCase();
    await user.type(await screen.findByLabelText(/Reply to the customer/), ' We refunded TXN-9999999.');
    await user.click(screen.getByRole('button', { name: 'Review and send' }));
    await user.type(screen.getByLabelText('Why did you change the reply? (required)'), 'added detail');
    await user.click(screen.getByRole('button', { name: 'Send RM 100.00 refund' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Not sent: the reply failed the self-check.');
    expect(screen.getByRole('alert')).toHaveTextContent('TXN-9999999');
    expect(api.cases.find((c) => c.complaint_id === 'CMP-P1')?.status).toBe('PENDING_APPROVAL');
  });

  it("says the reply is edited instead of showing the draft's self-check", async () => {
    installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await openCase();
    expect(screen.getByText('Self-check verified')).toBeInTheDocument();
    await user.type(await screen.findByLabelText(/Reply to the customer/), ' Edited.');
    expect(screen.queryByText('Self-check verified')).not.toBeInTheDocument();
    expect(screen.getByText('The self-check runs again on your text when you send it')).toBeInTheDocument();
  });

  it('rejects only with a reason, and sends it', async () => {
    const api = installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await openCase();
    await user.click(await screen.findByRole('button', { name: 'Reject' }));
    const confirm = screen.getByRole('button', { name: 'Reject case' });
    expect(confirm).toBeDisabled();
    expect(api.calls.some((c) => c.path === '/cases/CMP-P1/reject')).toBe(false);
    await user.type(screen.getByLabelText('Reason for rejecting (required)'), 'journal shows full dispense');
    await user.click(confirm);
    expect(await screen.findByText('CMP-P1 rejected. No reply was sent; it is in Rejected for you to handle.'))
      .toBeInTheDocument();
    expect(api.calls.find((c) => c.path === '/cases/CMP-P1/reject')?.body).toEqual({ note: 'journal shows full dispense' });
  });
});

describe('fraud queue', () => {
  it('sends the holding reply and keeps the case with the fraud team', async () => {
    const api = installFakeApi();
    const { user } = renderApp('/fraud', { as: 'fraud1' });
    await openCase();
    expect(screen.queryByRole('button', { name: /Review and send|Approve/ })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Send holding reply' }));
    expect(await screen.findByText('CMP-FRAUD: holding reply sent. The case stays with the fraud team.')).toBeInTheDocument();
    expect(await screen.findByText(/Holding reply sent by fraud1/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Fraud queue (1)' })).toBeInTheDocument();
    expect(api.cases.find((c) => c.complaint_id === 'CMP-FRAUD')?.status).toBe('FRAUD_QUEUE');
  });
});

describe('rejected cases', () => {
  it('lists them with who rejected each one and why', async () => {
    installFakeApi([makeCase('CMP-REJ', { status: 'REJECTED', audit: [
      { ts: '2026-10-22 10:00:00', actor: 'agent', action: 'decided', detail: '{}' },
      { ts: '2026-10-22 11:00:00', actor: 'officer1', action: 'rejected', detail: 'wrong transaction matched' },
      { ts: '2026-10-22 11:00:00', actor: 'officer1', action: 'human_action', detail: '{"action":"reject"}' },
    ] })]);
    renderApp('/rejected', { as: 'officer1' });
    expect(await screen.findByRole('heading', { name: 'Rejected: handle manually (1)' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'officer1' })).toBeInTheDocument();          // Handled by
    expect(await screen.findByText(/Rejected by officer1 .*: wrong transaction matched/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument();
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
