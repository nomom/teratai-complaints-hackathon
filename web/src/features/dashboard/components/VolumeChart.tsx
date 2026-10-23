import { clsx } from 'clsx';
import { useId, useState, type KeyboardEvent } from 'react';

import { compact, niceTicks, STATUS_GROUPS, type Bucket, type Column } from '../lib/series';
import styles from './charts.module.css';

const MAX_X_LABELS = 7;

/**
 * Complaints received per day or week, stacked by where each case is now. Pointer or arrow keys pick a column and
 * the readout lists every group in it; the table under the chart holds the same numbers for anyone not using it.
 */
export function VolumeChart({ columns, bucket }: { columns: Column[]; bucket: Bucket }) {
  const id = useId();
  const [active, setActive] = useState<number | null>(null);
  const groups = STATUS_GROUPS.filter((g) => columns.some((c) => c.counts[g.key]));
  const ticks = niceTicks(Math.max(...columns.map((c) => c.total), 0));
  const top = ticks[ticks.length - 1];
  const every = Math.ceil(columns.length / MAX_X_LABELS);
  const current = active !== null ? columns[active] : null;
  const unit = bucket === 'week' ? 'week' : 'day';
  const busiest = columns.reduce<Column | null>((best, c) => (!best || c.total > best.total ? c : best), null);

  const move = (e: KeyboardEvent) => {
    const last = columns.length - 1;
    const next = { ArrowRight: (active ?? -1) + 1, ArrowLeft: (active ?? last + 1) - 1, Home: 0, End: last }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    setActive(Math.min(Math.max(next, 0), last));
  };

  return (
    <figure className={styles.figure}>
      <ul className={styles.legend} aria-label="Status">
        {groups.map((g) => (
          <li key={g.key}>
            <span className={styles.swatch} style={{ background: g.color }} aria-hidden />
            {g.label}
            <span className={styles.legendCount}>
              {columns.reduce((sum, c) => sum + (c.counts[g.key] ?? 0), 0).toLocaleString('en-MY')}
            </span>
          </li>
        ))}
      </ul>

      <div className={styles.chart}>
        <div className={styles.yAxis} aria-hidden>
          {ticks.map((t) => (
            <span key={t} style={{ bottom: `${(t / top) * 100}%` }}>{compact(t)}</span>
          ))}
        </div>
        <div
          className={styles.plot}
          role="group"
          tabIndex={0}
          aria-label={`Complaints received per ${unit}. Use the left and right arrow keys to read each ${unit}.`}
          aria-describedby={`${id}-readout`}
          onKeyDown={move}
          onPointerLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
        >
          {ticks.map((t) => (
            <span key={t} className={styles.gridline} style={{ bottom: `${(t / top) * 100}%` }} aria-hidden />
          ))}
          <div className={styles.columns} style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}>
            {columns.map((c, i) => (
              <div key={c.start} className={clsx(styles.slot, i === active && styles.slotActive)}
                onPointerEnter={() => setActive(i)} aria-hidden>
                <div className={styles.stack} style={{ height: `${(c.total / top) * 100}%` }}>
                  {[...groups].reverse().filter((g) => c.counts[g.key]).map((g) => (
                    <span key={g.key} className={styles.segment} style={{ flexGrow: c.counts[g.key], background: g.color }} />
                  ))}
                </div>
              </div>
            ))}
          </div>
          {current && (
            <div className={styles.tooltip} aria-hidden
              style={{ left: `${((active! + 0.5) / columns.length) * 100}%` }}
              data-side={active! > columns.length / 2 ? 'left' : 'right'}>
              <p className={styles.tooltipTitle}>{current.label}</p>
              <p className={styles.tooltipRow}><strong>{current.total.toLocaleString('en-MY')}</strong> received</p>
              {groups.filter((g) => current.counts[g.key]).map((g) => (
                <p key={g.key} className={styles.tooltipRow}>
                  <span className={styles.lineKey} style={{ background: g.color }} />
                  <strong>{current.counts[g.key].toLocaleString('en-MY')}</strong> {g.label}
                </p>
              ))}
            </div>
          )}
        </div>
        <div className={styles.xAxis} aria-hidden style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}>
          {columns.map((c, i) => (
            <span key={c.start}>{i % every === 0 ? c.label.replace('Week of ', '') : ''}</span>
          ))}
        </div>
      </div>

      <p id={`${id}-readout`} className={styles.readout} aria-live="polite">
        {current
          ? `${current.label}: ${current.total} received. ${groups.filter((g) => current.counts[g.key])
            .map((g) => `${g.label} ${current.counts[g.key]}`).join(', ')}.`
          : busiest && busiest.total > 0 && `Busiest ${unit}: ${busiest.label}, ${busiest.total.toLocaleString('en-MY')} received.`}
      </p>

      <details className={styles.tableToggle}>
        <summary>Show as table</summary>
        <div className={styles.tableFrame}>
          <table className={styles.table}>
            <caption className="visually-hidden">Complaints received per {unit}, by status</caption>
            <thead>
              <tr>
                <th scope="col">{bucket === 'week' ? 'Week of' : 'Day'}</th>
                {groups.map((g) => <th key={g.key} scope="col" className={styles.number}>{g.label}</th>)}
                <th scope="col" className={styles.number}>Total</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((c) => (
                <tr key={c.start}>
                  <th scope="row">{c.label.replace('Week of ', '')}</th>
                  {groups.map((g) => <td key={g.key} className={styles.number}>{c.counts[g.key] ?? 0}</td>)}
                  <td className={styles.number}>{c.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
