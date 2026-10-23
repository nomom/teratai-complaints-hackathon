import { describe, expect, it } from 'vitest';

import type { DailyKpis } from '../types';
import { activeCount, daysBefore, DEFAULT_FILTERS, rangeError, toParams } from './filters';
import { bandOf, delta, fillDays, share } from './kpi';
import { autoBucket, compact, niceTicks, toColumns, valueLabel, weekStart } from './series';

describe('dashboard filters', () => {
  it('opens on the last 30 days, sends the chosen values, and counts what differs from that', () => {
    expect(toParams(DEFAULT_FILTERS).toString()).toBe('last_days=30');
    expect(activeCount(DEFAULT_FILTERS)).toBe(0);
    const f = { ...DEFAULT_FILTERS, period: 'all', values: { ...DEFAULT_FILTERS.values, category: 'FEE_DISPUTE', outcome: 'NONE' } };
    expect(toParams(f).toString()).toBe('category=FEE_DISPUTE&outcome=NONE');
    expect(activeCount(f)).toBe(3);
  });

  it('sends a custom range only when it is the right way round', () => {
    const custom = { ...DEFAULT_FILTERS, period: 'custom', from: '2026-09-01', to: '2026-09-30' };
    expect(toParams(custom).toString()).toBe('date_from=2026-09-01&date_to=2026-09-30');
    expect(toParams({ ...custom, to: '' }).toString()).toBe('date_from=2026-09-01');
    const backwards = { ...custom, from: '2026-09-30', to: '2026-09-01' };
    expect(rangeError(backwards)).toBeTruthy();
    expect(toParams(backwards).toString()).toBe('');
  });

  it('counts days across months', () => {
    expect(daysBefore('2026-09-01', 1)).toBe('2026-08-31');
    expect(daysBefore('2026-09-30', -1)).toBe('2026-10-01');
  });
});

describe('scorecard figures', () => {
  it('says how a figure moved, and whether that is good', () => {
    expect(delta(120, 100, 'down')).toMatchObject({ percent: 20, direction: 'up', tone: 'bad', text: 'Up 20%' });
    expect(delta(80, 100, 'down')).toMatchObject({ direction: 'down', tone: 'good', text: 'Down 20%' });
    expect(delta(80, 100, 'neutral').tone).toBe('neutral');
    expect(delta(100, 100, 'up')).toMatchObject({ direction: 'flat', tone: 'neutral', text: 'No change' });
    expect(delta(5, 0, 'up')).toMatchObject({ percent: null, text: 'New, none before' });
    expect(delta(0, 0, 'up').text).toBe('No change');
  });

  it('gives a trend a value for every day, zero where nothing came in', () => {
    const day = (d: string, received: number) => ({ day: d, received }) as DailyKpis;
    const points = fillDays([day('2026-09-02', 3), day('2026-09-04', 1)], (d) => d.received, '2026-09-01', '2026-09-04');
    expect(points.map((p) => p.value)).toEqual([0, 3, 0, 1]);
    expect(fillDays([], (d) => d.received).length).toBe(0);
  });

  it('bands a rate against its target', () => {
    const target = { good: 90, fair: 75 };
    expect([bandOf(95, target), bandOf(80, target), bandOf(10, target)]).toEqual(['good', 'fair', 'poor']);
    expect(share(1, 3)).toBe(33);
    expect(share(1, 0, 100)).toBe(100);
  });
});

describe('dashboard series', () => {
  const rows = [
    { day: '2026-09-01', status: 'RESOLVED' as const, n: 3 },
    { day: '2026-09-01', status: 'ANSWERED' as const, n: 1 },
    { day: '2026-09-03', status: 'FRAUD_QUEUE' as const, n: 2 },
  ];

  it('fills the days in between and groups statuses', () => {
    const columns = toColumns(rows, 'day');
    expect(columns.map((c) => [c.start, c.total])).toEqual([['2026-09-01', 4], ['2026-09-02', 0], ['2026-09-03', 2]]);
    expect(columns[0].counts).toEqual({ auto: 4 });
    expect(columns[2].counts).toEqual({ fraud: 2 });
  });

  it('groups by week from Monday', () => {
    expect(weekStart('2026-09-06')).toBe('2026-08-31');           // a Sunday
    expect(weekStart('2026-09-07')).toBe('2026-09-07');           // a Monday
    const weeks = toColumns([...rows, { day: '2026-09-08', status: 'REJECTED' as const, n: 1 }], 'week');
    expect(weeks.map((c) => [c.label, c.total])).toEqual([['Week of 31 Aug', 6], ['Week of 7 Sep', 1]]);
  });

  it('picks weeks for over six weeks of data', () => {
    expect(autoBucket(rows)).toBe('day');
    expect(autoBucket([rows[0], { day: '2026-11-01', status: 'RESOLVED', n: 1 }])).toBe('week');
    expect(autoBucket([])).toBe('day');
  });

  it('makes round axis steps and compact numbers', () => {
    expect(niceTicks(9)).toEqual([0, 2.5, 5, 7.5, 10]);
    expect(niceTicks(40)).toEqual([0, 10, 20, 30, 40]);
    expect(niceTicks(0)).toEqual([0, 1]);
    expect(compact(950)).toBe('950');
    expect(compact(12900)).toBe('12.9K');
  });

  it('reads codes as words', () => {
    expect(valueLabel('status', 'PENDING_APPROVAL')).toBe('Approval queue');
    expect(valueLabel('outcome', 'NONE')).toBe('Not decided yet');
    expect(valueLabel('language', 'MS')).toBe('Malay');
    expect(valueLabel('category', 'ATM_NOT_DISPENSED')).toBe('ATM not dispensed');
  });
});
