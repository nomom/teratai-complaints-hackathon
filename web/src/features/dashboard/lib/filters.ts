import { ANY } from '@/features/cases/lib/filters';

import type { Dimension } from '../types';

export { ANY };

/** The filters in the order they appear above the charts. */
export const DIMENSIONS: Dimension[] = ['status', 'route', 'category', 'outcome', 'priority', 'channel', 'language'];

export interface DashboardFilters {
  /** A preset ('all', '7', '30', '90' days) or 'custom' for the from/to boxes. */
  period: string;
  from: string;
  to: string;
  values: Record<Dimension, string>;
}

/** A scorecard compares with the period before, so it opens on the last 30 days ("all dates" has nothing before it). */
export const DEFAULT_PERIOD = '30';

export const DEFAULT_FILTERS: DashboardFilters = {
  period: DEFAULT_PERIOD,
  from: '',
  to: '',
  values: { status: ANY, route: ANY, category: ANY, outcome: ANY, priority: ANY, channel: ANY, language: ANY },
};

export const PERIODS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: 'all', label: 'All dates' },
  { value: 'custom', label: 'Custom range' },
];

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** "2026-09-30" minus n days, as YYYY-MM-DD (UTC arithmetic, so no time zone can shift the day). */
export function daysBefore(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

/** The custom range is the wrong way round. */
export const rangeError = (f: DashboardFilters): string | undefined =>
  f.period === 'custom' && ISO_DAY.test(f.from) && ISO_DAY.test(f.to) && f.from > f.to
    ? 'Must be on or after the "from" date.'
    : undefined;

/**
 * The query string for GET /dashboard. A preset is sent as last_days: the bank's data ends on a fixed day (30 Sep
 * 2026), long before today, so the API counts back from the newest complaint the viewer can see, not from today.
 * A custom range the wrong way round is left out rather than sent (it is a 422).
 */
export function toParams(f: DashboardFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (f.period === 'custom') {
    if (!rangeError(f)) {
      if (ISO_DAY.test(f.from)) params.set('date_from', f.from);
      if (ISO_DAY.test(f.to)) params.set('date_to', f.to);
    }
  } else if (f.period !== 'all') {
    params.set('last_days', f.period);
  }
  DIMENSIONS.forEach((d) => {
    if (f.values[d] !== ANY) params.set(d, f.values[d]);
  });
  return params;
}

/** How many filters differ from the defaults (a date range other than the last 30 days counts as one). */
export const activeCount = (f: DashboardFilters): number =>
  (f.period !== DEFAULT_PERIOD ? 1 : 0) + DIMENSIONS.filter((d) => f.values[d] !== ANY).length;
