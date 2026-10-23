import { clsx } from 'clsx';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { useState } from 'react';

import type { Delta } from '../lib/kpi';
import { shortDay } from '../lib/series';
import styles from './charts.module.css';
import { Sparkline } from './Sparkline';

interface ScorecardProps {
  label: string;
  value: string;
  /** A short line under the figure, e.g. what is still waiting. */
  note?: string;
  points: { day: string; value: number }[];
  kind?: 'line' | 'bars';
  /** How a day's value reads under the pointer. */
  format: (value: number) => string;
  /** Change against the period before; null for "all dates". */
  change: Delta | null;
  /** "the previous 30 days" */
  comparedWith: string;
}

const ARROW = { up: ArrowUpRight, down: ArrowDownRight, flat: Minus };

/** A KPI: the figure, a daily trend, and how it moved against the period before (arrow plus words, never colour alone). */
export function Scorecard({ label, value, note, points, kind, format, change, comparedWith }: ScorecardProps) {
  const [active, setActive] = useState<number | null>(null);
  const point = active !== null ? points[active] : null;
  const Arrow = change ? ARROW[change.direction] : Minus;

  return (
    <article className={styles.scorecard} aria-label={label}>
      <h2 className={styles.cardLabel}>{label}</h2>
      <p className={styles.scoreValue}>{value}</p>
      {note && <p className={styles.scoreNote}>{note}</p>}
      <Sparkline points={points} kind={kind} active={active} onActive={setActive} />
      <p className={styles.sparkReadout} aria-hidden>
        {point
          ? `${shortDay(point.day)}: ${format(point.value)}`
          : points.length > 0 && `Per day, ${shortDay(points[0].day)} to ${shortDay(points[points.length - 1].day)}`}
      </p>
      <p className={styles.change}>
        {change ? (
          <>
            <span className={clsx(styles.changeBadge, styles[change.tone])}>
              <Arrow aria-hidden />
              {change.text}
            </span>
            <span className={styles.changeContext}>on {comparedWith}</span>
          </>
        ) : (
          <span className={styles.changeContext}>Pick a date range to compare with the period before.</span>
        )}
      </p>
    </article>
  );
}
