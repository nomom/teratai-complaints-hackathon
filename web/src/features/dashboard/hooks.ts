import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { caseKeys } from '@/features/cases/hooks';

import { getDashboard } from './api';

/** Slower than the queues (5 s): the charts are an overview, and each refresh counts every case. */
export const DASHBOARD_REFRESH_MS = 30000;

/**
 * Under caseKeys.all, so an approve or reject anywhere refreshes the charts too. While new filters load, the previous
 * charts stay on screen (dimmed by the page) instead of flashing a spinner.
 */
export const useDashboard = (params: URLSearchParams) =>
  useQuery({
    queryKey: [...caseKeys.all, 'dashboard', params.toString()],
    queryFn: () => getDashboard(params),
    refetchInterval: DASHBOARD_REFRESH_MS,
    placeholderData: keepPreviousData,
  });
