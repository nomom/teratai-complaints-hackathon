import styles from './charts.module.css';

export interface Slice {
  value: string;
  label: string;
  n: number;
  color: string;
}

interface DonutProps {
  label: string;
  slices: Slice[];
  /** The value this dimension is filtered to, or null. */
  selected: string | null;
  onSelect: (value: string | null) => void;
}

const GAP = 0.8;        // the surface gap between slices, in percent of the ring

/**
 * A part-to-whole split for a few values (two to four). The legend beside it carries every number and is the
 * control: selecting a row filters the dashboard to it, again clears it.
 */
export function Donut({ label, slices, selected, onSelect }: DonutProps) {
  const total = slices.reduce((sum, s) => sum + s.n, 0);
  const gap = slices.filter((s) => s.n > 0).length > 1 ? GAP : 0;
  let offset = 0;

  return (
    <article className={styles.donutCard} aria-label={label}>
      <h2 className={styles.cardLabel}>{label}</h2>
      <div className={styles.donutBody}>
        <div className={styles.donut}>
          <svg viewBox="0 0 42 42" aria-hidden>
            <circle cx={21} cy={21} r={15.915} className={styles.donutTrack} />
            {total > 0 && slices.map((s) => {
              const length = (s.n / total) * 100;
              const start = offset;
              offset += length;
              if (length <= gap) return null;
              return (
                <circle key={s.value} cx={21} cy={21} r={15.915} className={styles.donutSlice}
                  style={{ stroke: s.color }} strokeDasharray={`${length - gap} ${100 - length + gap}`}
                  strokeDashoffset={25 - start} data-dim={selected !== null && selected !== s.value ? '' : undefined}>
                  <title>{`${s.label}: ${s.n.toLocaleString('en-MY')}`}</title>
                </circle>
              );
            })}
          </svg>
          <p className={styles.donutCenter}>
            <strong>{total.toLocaleString('en-MY')}</strong>
            <span>cases</span>
          </p>
        </div>
        <ul className={styles.donutLegend} aria-label={`${label}: select one to filter`}>
          {slices.map((s) => {
            const on = selected === s.value;
            return (
              <li key={s.value}>
                <button type="button" className={styles.legendRow} aria-pressed={on}
                  title={on ? 'Show every value again' : `Show only ${s.label}`} onClick={() => onSelect(on ? null : s.value)}>
                  <span className={styles.swatch} style={{ background: s.color }} aria-hidden />
                  <span className={styles.legendName}>{s.label}</span>
                  <span className={styles.legendNumber}>{s.n.toLocaleString('en-MY')}</span>
                  <span className={styles.legendShare}>{total ? Math.round((s.n / total) * 100) : 0}%</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </article>
  );
}
