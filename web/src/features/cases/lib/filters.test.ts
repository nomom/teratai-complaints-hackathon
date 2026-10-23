import { describe, expect, it } from 'vitest';

import type { CaseRow } from '../types';
import { activeCount, ANY, matchesFilters, NO_FILTERS, type CaseFilters } from './filters';

const row = (over: Partial<CaseRow>) => ({
  complaint_id: 'CMP-00244', customer_id: 'CUS-02394', matched_txn_id: 'TXN-0148619', category: 'ATM_NOT_DISPENSED',
  outcome: 'REFUND', priority: 'P2', refund_amount_myr: 550, ...over,
}) as CaseRow;

const only = (over: Partial<CaseFilters>) => ({ ...NO_FILTERS, ...over });

describe('case filters', () => {
  it('lets everything through with no filter', () => {
    expect(matchesFilters(row({}), NO_FILTERS)).toBe(true);
    expect(activeCount(NO_FILTERS)).toBe(0);
  });

  it('searches the complaint, customer and transaction IDs, in part, any case, ignoring spaces around it', () => {
    for (const search of ['cmp-00244', '00244', 'CUS-02394', '  cus-02394 ', 'txn-0148619']) {
      expect(matchesFilters(row({}), only({ search }))).toBe(true);
    }
    expect(matchesFilters(row({}), only({ search: 'CUS-00150' }))).toBe(false);
    expect(matchesFilters(row({ matched_txn_id: null }), only({ search: 'TXN' }))).toBe(false);
  });

  it('matches category, outcome and priority exactly', () => {
    expect(matchesFilters(row({}), only({ category: 'ATM_NOT_DISPENSED', outcome: 'REFUND', priority: 'P2' }))).toBe(true);
    expect(matchesFilters(row({}), only({ category: 'FEE_DISPUTE' }))).toBe(false);
    expect(matchesFilters(row({}), only({ outcome: 'DECLINE' }))).toBe(false);
    expect(matchesFilters(row({}), only({ priority: 'P1' }))).toBe(false);
    expect(matchesFilters(row({ category: null }), only({ category: ANY }))).toBe(true);
  });

  it('keeps refunds inside the range, both ends included, and leaves out undecided cases', () => {
    expect(matchesFilters(row({}), only({ refundMin: '550', refundMax: '550' }))).toBe(true);
    expect(matchesFilters(row({}), only({ refundMin: '500.01' }))).toBe(true);
    expect(matchesFilters(row({}), only({ refundMax: '500' }))).toBe(false);
    expect(matchesFilters(row({ refund_amount_myr: 0 }), only({ refundMax: '0' }))).toBe(true);
    expect(matchesFilters(row({ refund_amount_myr: null }), only({ refundMin: '0' }))).toBe(false);
    expect(matchesFilters(row({ refund_amount_myr: null }), only({ refundMin: 'abc' }))).toBe(true);   // not a number: ignored
  });

  it('counts each narrowing filter once, the refund range as one', () => {
    expect(activeCount(only({ search: ' x ', category: 'FEE_DISPUTE', refundMin: '1', refundMax: '9' }))).toBe(3);
    expect(activeCount(only({ search: '   ' }))).toBe(0);
  });
});
