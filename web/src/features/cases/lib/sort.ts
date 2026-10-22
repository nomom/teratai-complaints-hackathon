import type { CaseRow } from '../types';
import { slaLeft } from './sla';

const PRIORITY_RANK: Record<string, number> = { P1: 0, P2: 1, P3: 2 };

type SortFields = Pick<CaseRow, 'priority' | 'status' | 'sla_due' | 'received_at' | 'created_at' | 'updated_at'>;

/** The most urgent first: priority, then least time left to acknowledge; closed cases and ties newest first. */
export function sortByUrgency<T extends SortFields>(rows: T[], now: Date = new Date()): T[] {
  const keyed = rows.map((row) => ({
    row,
    rank: PRIORITY_RANK[row.priority ?? ''] ?? 9,
    left: slaLeft(row, now) ?? Number.POSITIVE_INFINITY,
  }));
  keyed.sort((a, b) => a.rank - b.rank || a.left - b.left || b.row.updated_at.localeCompare(a.row.updated_at));
  return keyed.map((k) => k.row);
}
