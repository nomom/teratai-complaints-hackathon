import { apiRequest } from '@/lib/apiClient';

import type { Profile, Statement } from './types';

/** The signed-in customer's own records (customers only: staff get 403). */
export const getProfile = () => apiRequest<Profile>('/me/profile');
export const getStatement = () => apiRequest<Statement>('/me/transactions');
