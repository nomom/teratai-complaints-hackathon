import type { DailyKpis } from '../types';
import { daysBefore } from './filters';

/** Which way a figure should move: down for a backlog, up for automation; neutral when neither is better. */
export type Better = 'up' | 'down' | 'neutral';

export interface Delta {
  /** Rounded percentage change, or null when the period before had none to compare with. */
  percent: number | null;
  direction: 'up' | 'down' | 'flat';
  tone: 'good' | 'bad' | 'neutral';
  text: string;
}

/** "Up 12%", "Down 3%", "No change", or "New" (nothing in the period before) - read with the period it compares to. */
export function delta(current: number, previous: number, better: Better): Delta {
  const direction = current > previous ? 'up' : current < previous ? 'down' : 'flat';
  const tone = direction === 'flat' || better === 'neutral' ? 'neutral' : direction === better ? 'good' : 'bad';
  if (previous === 0) {
    return { percent: null, direction, tone, text: current === 0 ? 'No change' : 'New, none before' };
  }
  const percent = Math.round(((current - previous) / previous) * 100);
  if (percent === 0) return { percent: 0, direction: 'flat', tone: 'neutral', text: 'No change' };
  return { percent, direction, tone, text: `${direction === 'up' ? 'Up' : 'Down'} ${Math.abs(percent)}%` };
}

/** One value per day from `from` to `to`, zero on days with no complaints, so a trend line never skips a gap. */
export function fillDays(daily: DailyKpis[], pick: (d: DailyKpis) => number, from?: string | null,
  to?: string | null): { day: string; value: number }[] {
  const first = from ?? daily[0]?.day;
  const last = to ?? daily[daily.length - 1]?.day;
  if (!first || !last || first > last) return [];
  const byDay = new Map(daily.map((d) => [d.day, pick(d)]));
  const out: { day: string; value: number }[] = [];
  for (let day = first; day <= last && out.length < 1000; day = daysBefore(day, -1)) {
    out.push({ day, value: byDay.get(day) ?? 0 });
  }
  return out;
}

/** a / b as a whole percentage; `empty` when there is nothing to divide by. */
export const share = (a: number, b: number, empty = 0): number => (b > 0 ? Math.round((a / b) * 100) : empty);

/**
 * Where a gauge turns from red to amber to green. Placeholders until the bank sets its own service levels: change
 * them here and every gauge follows.
 */
export const TARGETS = {
  /** Cases resolved with no person involved. */
  automation: { good: 40, fair: 25 },
  /** Open cases still inside the time allowed to acknowledge the customer. */
  onTime: { good: 90, fair: 75 },
};

export type Band = 'good' | 'fair' | 'poor';
export const bandOf = (value: number, target: { good: number; fair: number }): Band =>
  value >= target.good ? 'good' : value >= target.fair ? 'fair' : 'poor';

export const BAND_COLOR: Record<Band, string> = { good: 'var(--success)', fair: 'var(--warning)', poor: 'var(--error)' };
export const BAND_LABEL: Record<Band, string> = { good: 'On target', fair: 'Below target', poor: 'Well below target' };

/** Colours for the splits, from the status tones the badges already use, in a fixed order per value. */
export const OUTCOME_COLOR: Record<string, string> = {
  REFUND: 'var(--success)', DECLINE: 'var(--border-strong)', INVESTIGATE: 'var(--error)', INFO_ONLY: 'var(--info)',
  NONE: 'var(--warning)',
};
export const OUTCOME_ORDER = ['REFUND', 'DECLINE', 'INVESTIGATE', 'INFO_ONLY', 'NONE'];

/** Priority is ordered, so it takes steps of one hue (strongest for P1) rather than status colours. */
export const PRIORITY_COLOR: Record<string, string> = {
  P1: 'var(--chart-seq-1)', P2: 'var(--chart-seq-2)', P3: 'var(--chart-seq-3)', NONE: 'var(--border-strong)',
};
/** Two languages: the two ends of the same steps, far enough apart to tell at a glance. */
export const LANGUAGE_COLOR: Record<string, string> = {
  EN: 'var(--chart-seq-1)', MS: 'var(--chart-seq-3)', NONE: 'var(--border-strong)',
};
