import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

function signedInCustomer(path: string) {
  const api = installFakeApi();
  api.signUp('CUS-00150', 'secret1');
  return { api, ...renderApp(path, { as: 'CUS-00150' }) };
}

describe('the account menu', () => {
  it('opens Profile and Transactions for a customer, outside the page list', async () => {
    const { user, router } = signedInCustomer('/my-cases');
    await user.click(await screen.findByRole('button', { name: 'Ravi a/l Rajan, account menu' }));
    const menu = await screen.findByRole('navigation', { name: 'Account' });
    expect(within(menu).getAllByRole('link').map((link) => link.textContent)).toEqual(['Profile', 'Transactions']);
    expect(screen.getByText('Signed in as CUS-00150')).toBeInTheDocument();

    await user.click(within(menu).getByRole('link', { name: 'Profile' }));
    expect(await screen.findByRole('heading', { name: 'Profile' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/profile');
    expect(screen.queryByRole('navigation', { name: 'Account' })).not.toBeInTheDocument();     // closed on the way
  });

  it('gives staff only the theme and Log out', async () => {
    installFakeApi();
    const { user } = renderApp('/approval', { as: 'officer1' });
    await user.click(await screen.findByRole('button', { name: 'Aisyah binti Rahman, account menu' }));
    expect(await screen.findByRole('button', { name: 'Log out' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Account' })).not.toBeInTheDocument();
  });

  it("keeps staff out of a customer's own pages", async () => {
    installFakeApi();
    const { router } = renderApp('/transactions', { as: 'officer1' });
    expect(await screen.findByRole('heading', { name: 'Approval queue (2)' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/approval');
  });
});

describe('Profile', () => {
  it("shows the customer's details and accounts, each linking to its transactions", async () => {
    signedInCustomer('/profile');
    expect(await screen.findByRole('heading', { name: 'Ravi a/l Rajan' })).toBeInTheDocument();
    expect(screen.getByText('Shah Alam, Selangor')).toBeInTheDocument();
    expect(screen.getByText('English')).toBeInTheDocument();
    expect(screen.getByText('14 May 1990')).toBeInTheDocument();
    const card = screen.getByRole('link', { name: 'Credit Card Classic ACC-000301: view transactions' });
    expect(card).toHaveAttribute('href', '/transactions?account=ACC-000301');
  });
});

describe('Transactions', () => {
  it('lists every transaction by month, newest first, with money in and out', async () => {
    signedInCustomer('/transactions');
    expect(await screen.findByRole('heading', { name: 'September 2026' })).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent))
      .toEqual(['September 2026', 'August 2026', 'July 2026']);
    expect(screen.getByText('+RM 250.00')).toBeInTheDocument();
    expect(screen.getByText('-RM 12.45')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('4 transactions')).toBeInTheDocument();
    // the failed charge moved no money, so money out is FoodKu and the ATM only
    expect(screen.getByText('RM 212.45')).toBeInTheDocument();
  });

  it('offers Report only inside the 45-day window', async () => {
    signedInCustomer('/transactions');
    await screen.findByRole('heading', { name: 'September 2026' });
    expect(screen.getAllByRole('button', { name: /^Report a problem/ })).toHaveLength(3);
    expect(screen.queryByRole('button', { name: /Shah Alam Branch/ })).not.toBeInTheDocument();
  });

  it('filters by search and by the account in the address', async () => {
    const { user } = signedInCustomer('/transactions?account=ACC-000301');
    expect(await screen.findByText('ShopLah Online')).toBeInTheDocument();
    expect(screen.queryByText('FoodKu')).not.toBeInTheDocument();
    expect(screen.getByText('1 transaction')).toBeInTheDocument();

    await user.type(screen.getByRole('searchbox', { name: 'Search' }), 'zzz');
    expect(await screen.findByText('No transactions match')).toBeInTheDocument();
  });

  it('finds a transaction by its reference', async () => {
    const { user } = signedInCustomer('/transactions');
    await user.type(await screen.findByRole('searchbox', { name: 'Search' }), 'txn-0000102');
    expect(await screen.findByText('Siti Aminah')).toBeInTheDocument();
    expect(screen.queryByText('FoodKu')).not.toBeInTheDocument();
  });

  it('opens a new complaint with the transaction already written in', async () => {
    const { user, router } = signedInCustomer('/transactions');
    await user.click(await screen.findByRole('button', { name: /^Report a problem with FoodKu/ }));
    expect(router.state.location.pathname).toBe('/new-complaint');
    expect(await screen.findByLabelText('Subject (optional)')).toHaveValue('FoodKu, RM 12.45 on 29 Sep 2026');
    expect(screen.getByLabelText(/What happened/)).toHaveValue(
      'Card e-Commerce TXN-0000101: RM 12.45, FoodKu, on 29 Sep 2026.\n\n');
  });
});
