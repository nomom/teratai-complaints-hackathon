import { useState, type FormEvent } from 'react';

import { useFlash } from '@/app/providers/FlashProvider';
import { Alert, Button, TextField } from '@/components/ui';
import { ApiError } from '@/lib/apiClient';

import * as authApi from '../api';

const MIN_PASSWORD = 4;

/** Two steps, as the API: check the customer ID, then create a password. Afterwards the customer logs in. */
export function SignUpForm({ onSignedUp }: { onSignedUp: () => void }) {
  const { flash } = useFlash();
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [entered, setEntered] = useState('');
  const [password, setPassword] = useState('');
  const [again, setAgain] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the server. Is the API running?');
    } finally {
      setBusy(false);
    }
  }

  function checkId(event: FormEvent) {
    event.preventDefault();
    void run(async () => setCustomerId((await authApi.verifyCustomer(entered)).customer_id));
  }

  function createPassword(event: FormEvent) {
    event.preventDefault();
    if (password !== again) {
      setError("The passwords don't match. Type the same password twice.");
      return;
    }
    void run(async () => {
      await authApi.signUp(customerId!, password);
      flash('success', `Signed up. Log in with ${customerId} and your new password.`);
      onSignedUp();
    });
  }

  if (!customerId) {
    return (
      <form onSubmit={checkId} noValidate>
        {error && <Alert tone="error">{error}</Alert>}
        <TextField label="Customer ID" placeholder="CUS-00150" value={entered}
          onChange={(e) => setEntered(e.target.value)} required />
        <Button type="submit" variant="primary" block loading={busy}>
          Continue
        </Button>
      </form>
    );
  }

  return (
    <form onSubmit={createPassword} noValidate>
      {error && <Alert tone="error">{error}</Alert>}
      <p style={{ marginBottom: 'var(--space-4)' }}>
        Create a password for customer ID <strong>{customerId}</strong>.
      </p>
      <TextField label="Password" type="password" autoComplete="new-password" hint={`At least ${MIN_PASSWORD} characters`}
        value={password} onChange={(e) => setPassword(e.target.value)} required />
      <TextField label="Confirm password" type="password" autoComplete="new-password" value={again}
        onChange={(e) => setAgain(e.target.value)} required />
      <Button type="submit" variant="primary" block loading={busy}>
        Sign up
      </Button>
      <Button variant="ghost" block onClick={() => setCustomerId(null)} style={{ marginTop: 'var(--space-2)' }}>
        Use a different customer ID
      </Button>
    </form>
  );
}
