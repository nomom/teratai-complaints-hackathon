import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi, makeCase } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

/** Four cases a manager sees, with different customers, categories, outcomes, priorities and refunds. */
function cases() {
  return [
    makeCase('CMP-00244', { customer_id: 'CUS-02394', category: 'ATM_NOT_DISPENSED', refund_amount_myr: 550,
      priority: 'P2', matched_txn_id: 'TXN-0148619', updated_at: '2026-10-22 11:04:00' }),
    makeCase('CMP-00387', { customer_id: 'CUS-02323', category: 'SCAM_TRANSFER', outcome: 'INVESTIGATE',
      refund_amount_myr: 0, priority: 'P1', route: 'FRAUD_TEAM', status: 'FRAUD_QUEUE', updated_at: '2026-10-22 11:03:00' }),
    makeCase('CMP-00001', { customer_id: 'CUS-00150', category: 'FAILED_TRANSFER', refund_amount_myr: 46.54,
      priority: 'P2', route: 'AUTO_RESOLVE', status: 'RESOLVED', updated_at: '2026-10-22 11:02:00' }),
    makeCase('CMP-00467', { customer_id: 'CUS-00001', category: 'FEE_DISPUTE', outcome: 'DECLINE', refund_amount_myr: 0,
      priority: 'P3', updated_at: '2026-10-22 11:01:00' }),
  ];
}

const shownIds = () =>
  within(screen.getByRole('table')).getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent);

async function openAllCases() {
  installFakeApi(cases());
  const view = renderApp('/cases', { as: 'manager1' });
  await screen.findByRole('heading', { name: 'All cases (4)' });
  return view;
}

describe('all cases: search and filters', () => {
  it('finds a case by customer ID or complaint ID, in part and in any case', async () => {
    const { user } = await openAllCases();
    const search = screen.getByRole('searchbox', { name: 'Search' });
    await user.type(search, 'cus-02394');
    expect(shownIds()).toEqual(['CMP-00244']);
    expect(screen.getByRole('heading', { name: 'All cases (1)' })).toBeInTheDocument();
    expect(screen.getByText('1 of 4 cases match 1 filter.')).toBeInTheDocument();

    await user.clear(search);
    await user.type(search, '00387');
    expect(shownIds()).toEqual(['CMP-00387']);
  });

  it('filters by policy category from the dropdown', async () => {
    const { user } = await openAllCases();
    await user.click(screen.getByRole('combobox', { name: 'Category' }));
    await user.click(await screen.findByRole('option', { name: 'Scam transfer' }));
    expect(shownIds()).toEqual(['CMP-00387']);
  });

  it('filters by a refund range, both ends included', async () => {
    const { user } = await openAllCases();
    await user.type(screen.getByRole('spinbutton', { name: 'Refund from (RM)' }), '40');
    await user.type(screen.getByRole('spinbutton', { name: 'Refund to (RM)' }), '550');
    expect(shownIds()).toEqual(['CMP-00244', 'CMP-00001']);
  });

  it('says so when the range is backwards, and when nothing matches', async () => {
    const { user } = await openAllCases();
    await user.type(screen.getByRole('spinbutton', { name: 'Refund from (RM)' }), '100');
    await user.type(screen.getByRole('spinbutton', { name: 'Refund to (RM)' }), '10');
    expect(screen.getByText('Must be at least the "from" amount.')).toBeInTheDocument();
    expect(screen.getByText('No cases match')).toBeInTheDocument();
  });

  it('combines filters, and Clear filters brings every case back', async () => {
    const { user } = await openAllCases();
    await user.click(screen.getByRole('combobox', { name: 'Outcome' }));
    await user.click(await screen.findByRole('option', { name: 'Refund' }));
    await user.click(screen.getByRole('combobox', { name: 'Priority' }));
    await user.click(await screen.findByRole('option', { name: 'P2' }));
    expect(shownIds()).toEqual(['CMP-00244', 'CMP-00001']);
    expect(screen.getByText('2 of 4 cases match 2 filters.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(shownIds()).toHaveLength(4);
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument();
  });

  it("filters only within an officer's own queue", async () => {
    installFakeApi(cases());
    const { user } = renderApp('/cases', { as: 'officer1' });
    await screen.findByRole('heading', { name: 'All cases (2)' });
    await user.type(screen.getByRole('searchbox', { name: 'Search' }), 'CUS-02323');      // a fraud case
    expect(screen.getByText('No cases match')).toBeInTheDocument();
  });
});
