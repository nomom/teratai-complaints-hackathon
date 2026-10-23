import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi, makeCase } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

// Received 1 to 3 Sep: all inside the default "last 30 days" (5 Aug to 3 Sep)
const cases = () => [
  makeCase('CMP-A', { category: 'FEE_DISPUTE', received_at: '2026-09-01 09:00', audit: [] }),
  makeCase('CMP-B', { status: 'APPROVED', received_at: '2026-09-02 09:00', refund_amount_myr: 20, audit: [
    { ts: '2026-10-22 11:00:00', actor: 'officer1', action: 'human_action', detail: '{"action": "edit_approve"}' },
  ] }),
  makeCase('CMP-FRAUD', { route: 'FRAUD_TEAM', status: 'FRAUD_QUEUE', outcome: 'INVESTIGATE', category: 'SCAM_TRANSFER',
    refund_amount_myr: null, received_at: '2026-09-02 10:00', audit: [] }),
  makeCase('CMP-AUTO', { route: 'AUTO_RESOLVE', status: 'RESOLVED', received_at: '2026-09-03 10:00', audit: [] }),
];

const card = (name: string) => screen.getByRole('article', { name });
const figure = (name: string) => within(card(name)).getAllByRole('paragraph')[0].textContent;
const ranking = (name: string) => within(card(name)).getByRole('table');

describe('dashboard', () => {
  it('shows the manager scorecards, rates, rankings and the people who acted', async () => {
    installFakeApi(cases());
    renderApp('/dashboard', { as: 'manager1' });
    expect(await screen.findByRole('heading', { name: 'Dashboard', level: 1 })).toBeInTheDocument();
    expect(await screen.findByText(/^4 cases\. Received 5 Aug 2026 to 3 Sep 2026\./)).toBeInTheDocument();
    expect(figure('Complaints received')).toBe('4');
    expect(figure('Waiting for a person')).toBe('2');
    expect(figure('Refunds sent')).toBe('RM 120.00');                                       // CMP-B 20 + CMP-AUTO 100
    expect(within(card('Automation rate')).getByText('25%')).toBeInTheDocument();          // 1 of 4
    expect(within(card('Automation rate')).getByText(/Below target of 40%/)).toBeInTheDocument();
    expect(within(card('Acknowledged on time')).getByText(/On target of 90%/)).toBeInTheDocument();
    expect(within(ranking('Top categories')).getAllByRole('rowheader')).toHaveLength(3);
    expect(screen.getByRole('combobox', { name: 'Route' })).toBeInTheDocument();
    const people = screen.getByRole('table', { name: 'Actions by person' });
    expect(within(people).getByRole('rowheader', { name: /Aisyah binti Rahman/ })).toBeInTheDocument();
  });

  it('compares each figure with the period before, in words', async () => {
    installFakeApi([...cases(), makeCase('CMP-OLD', { received_at: '2026-08-01 09:00', audit: [] })]);
    const { user } = renderApp('/dashboard', { as: 'manager1' });
    await screen.findByText(/^4 cases\./);
    expect(within(card('Complaints received')).getByText('Up 300%')).toBeInTheDocument();     // 4 against 1
    expect(within(card('Waiting for a person')).getByText('Up 100%')).toBeInTheDocument();
    expect(within(card('Complaints received')).getByText('on the previous 30 days')).toBeInTheDocument();
    await user.click(screen.getByRole('combobox', { name: 'Received' }));
    await user.click(await screen.findByRole('option', { name: 'All dates' }));
    expect(await screen.findByText(/^5 cases\./)).toBeInTheDocument();
    expect(within(card('Complaints received')).getByText(/Pick a date range to compare/)).toBeInTheDocument();
  });

  it("shows an officer only their queue's cases, with no route filter and no people", async () => {
    installFakeApi(cases());
    renderApp('/dashboard', { as: 'officer1' });
    expect(await screen.findByText(/^2 cases\./)).toBeInTheDocument();
    expect(figure('Waiting for a person')).toBe('1');                                        // CMP-A
    expect(screen.queryByRole('combobox', { name: 'Route' })).not.toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Actions by person' })).not.toBeInTheDocument();
    expect(within(ranking('Top categories')).queryByText('Scam transfer')).not.toBeInTheDocument();
  });

  it('filters every number by selecting a ranked name or a split, and clears it again', async () => {
    const api = installFakeApi(cases());
    const { user } = renderApp('/dashboard', { as: 'manager1' });
    await screen.findByText(/^4 cases\./);
    await user.click(within(ranking('Top categories')).getByRole('button', { name: 'Fee dispute' }));
    expect(await screen.findByText(/^1 cases\..*1 filter on\./)).toBeInTheDocument();
    expect(api.calls.at(-1)).toMatchObject({ path: '/dashboard', search: '?last_days=30&category=FEE_DISPUTE' });
    expect(within(ranking('Top categories')).getByRole('button', { name: 'Fee dispute' }))
      .toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(await screen.findByText(/^4 cases\./)).toBeInTheDocument();
    await user.click(within(card('Reply language')).getByRole('button', { name: /English/ }));
    expect(api.calls.at(-1)?.search).toBe('?last_days=30&language=EN');
  });

  it('filters from the dropdowns, and says when nothing matches', async () => {
    installFakeApi(cases());
    const { user } = renderApp('/dashboard', { as: 'manager1' });
    await screen.findByText(/^4 cases\./);
    await user.click(screen.getByRole('combobox', { name: 'Status' }));
    await user.click(await screen.findByRole('option', { name: 'Fraud queue' }));
    expect(await screen.findByText(/^1 cases\./)).toBeInTheDocument();
    await user.click(screen.getByRole('combobox', { name: 'Received' }));
    await user.click(await screen.findByRole('option', { name: 'Custom range' }));
    await user.type(screen.getByLabelText('From'), '2026-09-03');
    expect(await screen.findByText('No cases match')).toBeInTheDocument();
  });

  it('flags a custom range the wrong way round and does not send it', async () => {
    const api = installFakeApi(cases());
    const { user } = renderApp('/dashboard', { as: 'manager1' });
    await screen.findByText(/^4 cases\./);
    await user.click(screen.getByRole('combobox', { name: 'Received' }));
    await user.click(await screen.findByRole('option', { name: 'Custom range' }));
    await user.type(screen.getByLabelText('From'), '2026-09-03');
    await user.type(screen.getByLabelText('To'), '2026-09-01');
    expect(await screen.findByText('Must be on or after the "from" date.')).toBeInTheDocument();
    const sent = api.calls.filter((c) => c.path === '/dashboard').map((c) => c.search);
    expect(sent).toContain('?date_from=2026-09-03');                   // the "from" alone, before "to" was typed
    expect(sent.some((s) => s.includes('date_to'))).toBe(false);
  });

  it('reads the volume chart by keyboard and as a table', async () => {
    installFakeApi(cases());
    const { user } = renderApp('/dashboard', { as: 'manager1' });
    const plot = await screen.findByRole('group', { name: /Complaints received per day/ });
    plot.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByText('1 Sep: 1 received. Approval queue 1.')).toBeInTheDocument();
    await user.keyboard('{End}');
    expect(screen.getByText('3 Sep: 1 received. Resolved automatically 1.')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Complaints received per day, by status' });
    expect(within(table).getAllByRole('row')).toHaveLength(4);                         // header and three days
  });

  it('is not for customers', async () => {
    const api = installFakeApi(cases());
    api.signUp('CUS-00150', 'secret1');
    const { router } = renderApp('/dashboard', { as: 'CUS-00150' });
    expect(await screen.findByRole('heading', { name: /My cases/ })).toBeInTheDocument();
    expect(router.state.location.pathname).not.toBe('/dashboard');
    expect(api.calls.some((c) => c.path === '/dashboard')).toBe(false);
  });
});
