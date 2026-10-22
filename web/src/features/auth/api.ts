import { apiRequest } from '@/lib/apiClient';

import type { User } from './types';

interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

/** Staff username (officer1) or customer ID (CUS-00150), plus password. */
export const login = (username: string, password: string) =>
  apiRequest<LoginResponse>('/auth/login', { method: 'POST', body: { username, password } });

export const me = () => apiRequest<User>('/auth/me');

/** Sign-up step 1: is this a customer who hasn't signed up yet? Returns the normalised ID. */
export const verifyCustomer = (customerId: string) =>
  apiRequest<{ customer_id: string }>('/auth/signup/verify', { method: 'POST', body: { customer_id: customerId } });

/** Sign-up step 2: create the password. The customer then logs in. */
export const signUp = (customerId: string, password: string) =>
  apiRequest<{ customer_id: string }>('/auth/signup', {
    method: 'POST',
    body: { customer_id: customerId, password },
  });
