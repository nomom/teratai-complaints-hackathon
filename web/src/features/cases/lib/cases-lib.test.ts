import { describe, expect, it } from 'vitest';

import { duration, money, nice } from '@/lib/format';

import { slaLeft, slaText } from './sla';
import { sortByUrgency } from './sort';

const NOW = new Date(2026, 9, 22, 12, 0);

function row(id: string, priority: string | null, { status = 'PENDING_APPROVAL', hours = 24, updated = '2026-10-22 11:00:00' } = {}) {
  const due = new Date(2026, 8, 30, 10 + hours);
  const pad = (n: number) => String(n).padStart(2, '0');
  return {
    complaint_id: id, priority, status: status as 'PENDING_APPROVAL', received_at: '2026-09-30 10:00',
    sla_due: `${due.getFullYear()}-${pad(due.getMonth() + 1)}-${pad(due.getDate())} ${pad(due.getHours())}:00`,
    created_at: '2026-10-22 11:00:00', updated_at: updated,
  };
}

describe('format', () => {
  it('writes money with two decimals and a dash for none', () => {
    expect(money(1500)).toBe('RM 1,500.00');
    expect(money(null)).toBe('-');
  });
  it('turns codes into words', () => {
    expect(nice('ATM_NOT_DISPENSED')).toBe('ATM not dispensed');
    expect(nice(null)).toBe('-');
  });
  it('writes durations compactly', () => {
    expect(duration(90 * 60000)).toBe('1h 30m');
    expect(duration(-26 * 3600000)).toBe('1d 2h');
  });
});

describe('time left to acknowledge', () => {
  it('starts when the case entered the store', () => {
    // 24h window, stored an hour before NOW
    expect(slaLeft(row('A', 'P2'), NOW)).toBe(23 * 3600000);
    expect(slaText(slaLeft(row('A', 'P2', { hours: 0 }), NOW))).toBe('overdue 1h 00m');
  });
  it('is closed for a case that is no longer open', () => {
    expect(slaLeft(row('A', 'P2', { status: 'RESOLVED' }), NOW)).toBeNull();
  });
});

describe('queue order', () => {
  const ids = (rows: { complaint_id: string }[]) => rows.map((r) => r.complaint_id);

  it('puts priority before recency', () => {
    const rows = [row('P3-new', 'P3', { updated: '2026-10-22 11:59:00' }), row('P1-old', 'P1', { updated: '2026-10-01' })];
    expect(ids(sortByUrgency(rows, NOW))).toEqual(['P1-old', 'P3-new']);
  });
  it('puts the least time left first within a priority', () => {
    const rows = [row('plenty', 'P2', { hours: 48 }), row('tight', 'P2', { hours: 4 }), row('overdue', 'P2', { hours: 0 })];
    expect(ids(sortByUrgency(rows, NOW))).toEqual(['overdue', 'tight', 'plenty']);
  });
  it('orders closed cases by priority, then newest first', () => {
    const rows = [
      row('old', 'P2', { status: 'RESOLVED', updated: '2026-10-01 09:00:00' }),
      row('new', 'P2', { status: 'RESOLVED', updated: '2026-10-20 09:00:00' }),
      row('urgent', 'P1', { status: 'RESOLVED', updated: '2026-09-01 09:00:00' }),
    ];
    expect(ids(sortByUrgency(rows, NOW))).toEqual(['urgent', 'new', 'old']);
  });
});
