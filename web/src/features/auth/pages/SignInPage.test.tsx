import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

async function logIn(user: ReturnType<typeof renderApp>['user'], username: string, password: string) {
  await user.type(screen.getByLabelText('Username or customer ID'), username);
  await user.type(screen.getByLabelText('Password'), password);
  await user.click(screen.getByRole('button', { name: 'Log in' }));
}

describe('sign-in', () => {
  it('shows nothing but the sign-in page when signed out', async () => {
    installFakeApi();
    const { router } = renderApp('/approval');
    expect(await screen.findByRole('heading', { name: 'Complaints Ops' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/sign-in');
  });

  it('refuses a wrong password and stays on the sign-in page', async () => {
    installFakeApi();
    const { user } = renderApp('/sign-in');
    await logIn(user, 'officer1', 'wrong');
    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong username or password.');
    expect(screen.queryByText(/CMP-/)).not.toBeInTheDocument();
  });

  it("lands staff on their role's first page", async () => {
    installFakeApi();
    const { user, router } = renderApp('/sign-in');
    await logIn(user, 'officer1', '1234');
    expect(await screen.findByRole('heading', { name: 'Approval queue (2)' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/approval');
    expect(screen.getByText('Aisyah binti Rahman')).toBeInTheDocument();
  });

  it('tells a customer who has not signed up to sign up first', async () => {
    installFakeApi();
    const { user } = renderApp('/sign-in');
    await logIn(user, 'CUS-00150', 'secret1');
    expect(await screen.findByRole('alert')).toHaveTextContent('Please sign up first');
  });

  it('signs a customer up in two steps, refusing mismatched passwords', async () => {
    installFakeApi();
    const { user } = renderApp('/sign-in');
    await user.click(screen.getByRole('tab', { name: 'Sign up (customers)' }));
    await user.type(screen.getByLabelText('Customer ID'), 'CUS-99999');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('is not a Teratai Bank customer');

    await user.clear(screen.getByLabelText('Customer ID'));
    await user.type(screen.getByLabelText('Customer ID'), 'cus-00150');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText(/Create a password for customer ID/)).toHaveTextContent('CUS-00150');

    await user.type(screen.getByLabelText('Password'), 'secret1');
    await user.type(screen.getByLabelText('Confirm password'), 'secret2');
    await user.click(screen.getByRole('button', { name: 'Sign up' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("The passwords don't match");

    await user.clear(screen.getByLabelText('Confirm password'));
    await user.type(screen.getByLabelText('Confirm password'), 'secret1');
    await user.click(screen.getByRole('button', { name: 'Sign up' }));
    expect(await screen.findByText('Signed up. Log in with CUS-00150 and your new password.')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Log in' })).toHaveAttribute('aria-selected', 'true');
  });
});
