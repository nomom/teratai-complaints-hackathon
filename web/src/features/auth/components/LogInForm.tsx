import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';

import { homePath } from '@/app/navigation';
import { Alert, Button, TextField } from '@/components/ui';
import { ApiError } from '@/lib/apiClient';

import { useAuth } from '../AuthProvider';

export function LogInForm() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await signIn(username, password);
      navigate(homePath(user.role), { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the server. Is the API running?');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      {error && <Alert tone="error">{error}</Alert>}
      <TextField label="Username or customer ID" placeholder="officer1 or CUS-00150" autoComplete="username"
        value={username} onChange={(e) => setUsername(e.target.value)} required />
      <TextField label="Password" type="password" autoComplete="current-password"
        value={password} onChange={(e) => setPassword(e.target.value)} required />
      <Button type="submit" variant="primary" block loading={busy}>
        Log in
      </Button>
    </form>
  );
}
