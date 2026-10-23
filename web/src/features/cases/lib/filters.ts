import { nice } from '@/lib/format';

import type { CaseRow } from '../types';

/** "Any" in every filter dropdown. */
export const ANY = 'any';

/** The policy categories (data/complaint_policy.csv), in the policy's order. */
export const CATEGORIES = ['DUPLICATE_CHARGE', 'FAILED_TRANSFER', 'ATM_NOT_DISPENSED', 'UNAUTHORISED_CARD', 'SCAM_TRANSFER',
  'FEE_DISPUTE', 'SERVICE_QUALITY'];
export const OUTCOMES = ['REFUND', 'DECLINE', 'INVESTIGATE', 'INFO_ONLY'];
export const PRIORITIES = ['P1', 'P2', 'P3'];

export const optionsOf = (codes: string[], anyLabel: string) =>
  [{ value: ANY, label: anyLabel }, ...codes.map((code) => ({ value: code, label: nice(code) }))];

/** Everything typed or picked above the All cases table. The refund bounds stay text, as typed. */
export interface CaseFilters {
  search: string;
  category: string;
  outcome: string;
  priority: string;
  refundMin: string;
  refundMax: string;
}

export const NO_FILTERS: CaseFilters = { search: '', category: ANY, outcome: ANY, priority: ANY, refundMin: '', refundMax: '' };

/** A typed amount as a number, or null when the box is empty or not a number. */
export function amount(text: string): number | null {
  if (!text.trim()) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

/** How many filters are narrowing the list (the search counts as one). */
export const activeCount = (f: CaseFilters): number =>
  [f.search.trim() !== '', f.category !== ANY, f.outcome !== ANY, f.priority !== ANY,
    amount(f.refundMin) !== null || amount(f.refundMax) !== null].filter(Boolean).length;

/** Search: part of the complaint ID, customer ID or matched transaction, any case, spaces around it ignored.
 *  A refund bound leaves out cases with no refund amount at all. */
export function matchesFilters(row: CaseRow, f: CaseFilters): boolean {
  const needle = f.search.trim().toLowerCase();
  if (needle && ![row.complaint_id, row.customer_id, row.matched_txn_id ?? '']
    .some((id) => id.toLowerCase().includes(needle))) return false;
  if (f.category !== ANY && row.category !== f.category) return false;
  if (f.outcome !== ANY && row.outcome !== f.outcome) return false;
  if (f.priority !== ANY && row.priority !== f.priority) return false;
  const min = amount(f.refundMin);
  const max = amount(f.refundMax);
  if (min !== null || max !== null) {
    if (row.refund_amount_myr === null) return false;
    if (min !== null && row.refund_amount_myr < min) return false;
    if (max !== null && row.refund_amount_myr > max) return false;
  }
  return true;
}
