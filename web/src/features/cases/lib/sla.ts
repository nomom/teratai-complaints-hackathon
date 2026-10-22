import { duration, parseStamp } from '@/lib/format';

import type { CaseRow } from '../types';

const OPEN = new Set(['AWAITING_CUSTOMER', 'PENDING_APPROVAL', 'FRAUD_QUEUE']);

type SlaFields = Pick<CaseRow, 'status' | 'sla_due' | 'received_at' | 'created_at'>;

/**
 * Milliseconds left to acknowledge the customer, or null once the case is closed. The data lives in 2026, so the clock
 * starts when the case entered our store: left = (sla_due - received_at) - (now - created_at).
 */
export function slaLeft(row: SlaFields, now: Date = new Date()): number | null {
  if (!OPEN.has(row.status)) return null;
  const due = parseStamp(row.sla_due);
  const received = parseStamp(row.received_at);
  const created = parseStamp(row.created_at);
  if (!due || !received || !created) return null;
  return due.getTime() - received.getTime() - (now.getTime() - created.getTime());
}

export function slaText(left: number | null): string {
  if (left === null) return 'closed';
  return left < 0 ? `overdue ${duration(left)}` : `${duration(left)} left`;
}
