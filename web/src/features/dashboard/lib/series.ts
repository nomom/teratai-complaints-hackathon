import { PRIORITY, STATUS } from '@/features/cases/lib/status';
import type { CaseStatus } from '@/features/cases/types';
import { nice } from '@/lib/format';

import { NONE, type Dashboard, type Dimension } from '../types';
import { daysBefore } from './filters';

/**
 * The volume chart stacks cases by where they are, bottom up. Each group wears its status tone, the same colours as
 * the status badges, so a colour means one thing across the app. Fixed order: a filter never repaints a group.
 */
export interface StatusGroup {
  key: string;
  label: string;
  statuses: CaseStatus[];
  color: string;
}

export const STATUS_GROUPS: StatusGroup[] = [
  { key: 'auto', label: 'Resolved automatically', statuses: ['RESOLVED', 'ANSWERED', 'SENT'], color: 'var(--success)' },
  { key: 'approved', label: 'Approved and sent', statuses: ['APPROVED'], color: 'var(--primary)' },
  { key: 'approval', label: 'Approval queue', statuses: ['PENDING_APPROVAL'], color: 'var(--warning)' },
  { key: 'awaiting', label: 'Awaiting customer', statuses: ['AWAITING_CUSTOMER'], color: 'var(--info)' },
  { key: 'fraud', label: 'Fraud queue', statuses: ['FRAUD_QUEUE'], color: 'var(--error)' },
  { key: 'rejected', label: 'Rejected', statuses: ['REJECTED'], color: 'var(--border-strong)' },
];

const GROUP_OF = new Map(STATUS_GROUPS.flatMap((g) => g.statuses.map((s) => [s, g.key] as const)));

export type Bucket = 'day' | 'week';

/** One column of the volume chart: its first day, a label, and cases per status group. */
export interface Column {
  start: string;
  label: string;
  counts: Record<string, number>;
  total: number;
}

const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-09-07" -> "7 Sep". */
export const shortDay = (day: string): string => `${Number(day.slice(8, 10))} ${SHORT_MONTHS[Number(day.slice(5, 7)) - 1]}`;

/** The Monday on or before a day. */
export function weekStart(day: string): string {
  const weekday = new Date(`${day}T00:00:00Z`).getUTCDay();      // 0 Sunday .. 6 Saturday
  return daysBefore(day, (weekday + 6) % 7);
}

/** Day columns for over six weeks are too thin to read: weekly from there. */
export const autoBucket = (rows: Dashboard['by_day']): Bucket => {
  if (!rows.length) return 'day';
  const first = rows[0].day;
  const last = rows[rows.length - 1].day;
  return (Date.parse(last) - Date.parse(first)) / 86400000 > 42 ? 'week' : 'day';
};

/** Cases per day (or week) and status group, with a zero column for every day or week in between. */
export function toColumns(rows: Dashboard['by_day'], bucket: Bucket): Column[] {
  if (!rows.length) return [];
  const keyOf = (day: string) => (bucket === 'week' ? weekStart(day) : day);
  const byKey = new Map<string, Column>();
  const first = keyOf(rows[0].day);
  const last = keyOf(rows[rows.length - 1].day);
  for (let day = first; day <= last; day = daysBefore(day, bucket === 'week' ? -7 : -1)) {
    byKey.set(day, { start: day, label: bucket === 'week' ? `Week of ${shortDay(day)}` : shortDay(day), counts: {}, total: 0 });
  }
  rows.forEach(({ day, status, n }) => {
    const column = byKey.get(keyOf(day));
    const group = GROUP_OF.get(status);
    if (!column || !group) return;
    column.counts[group] = (column.counts[group] ?? 0) + n;
    column.total += n;
  });
  return [...byKey.values()];
}

/** Round, readable axis steps: 0 / 5 / 10, 0 / 50 / 100, 0 / 250 / 500 ... with the top at or above `max`. */
export function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let t = 0; t < max + step; t += step) ticks.push(Math.round(t * 100) / 100);
  return ticks.length > 1 ? ticks : [0, step];
}

/** 950, 1.3K, 12.9K, 1.2M. */
export function compact(n: number): string {
  if (Math.abs(n) < 1000) return n.toLocaleString('en-MY');
  return new Intl.NumberFormat('en-MY', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
}

const ROUTES: Record<string, string> = {
  AUTO_RESOLVE: 'Resolved automatically', HUMAN_APPROVAL: 'Approval queue', FRAUD_TEAM: 'Fraud team',
};
const LANGUAGES: Record<string, string> = { EN: 'English', MS: 'Malay' };

export const DIMENSION_LABEL: Record<Dimension, string> = {
  status: 'Status', route: 'Route', category: 'Category', outcome: 'Outcome', priority: 'Priority',
  channel: 'Channel', language: 'Reply language',
};

/** How a value reads on screen, e.g. PENDING_APPROVAL -> Approval queue, MS -> Malay. */
export function valueLabel(dimension: Dimension, value: string): string {
  if (value === NONE) return dimension === 'outcome' || dimension === 'route' ? 'Not decided yet' : 'Not set';
  switch (dimension) {
    case 'status': return STATUS[value as CaseStatus]?.label ?? value;
    case 'route': return ROUTES[value] ?? nice(value);
    case 'priority': return PRIORITY[value]?.label ?? value;
    case 'language': return LANGUAGES[value] ?? value;
    case 'channel': return value;
    default: return nice(value);
  }
}
