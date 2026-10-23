import { apiRequest } from '@/lib/apiClient';

import type { Dashboard } from './types';

/** Staff only; the API counts only the cases the signed-in role may see, whatever the filters say. */
export const getDashboard = (params: URLSearchParams) => {
  const query = params.toString();
  return apiRequest<Dashboard>(`/dashboard${query ? `?${query}` : ''}`);
};
