import styles from './charts.module.css';

export interface RankedRow {
  value: string;
  label: string;
  n: number;
  /** An extra figure in its own column, e.g. refunds sent. */
  extra?: string;
}

interface RankedTableProps {
  title: string;
  /** Heading of the first column, e.g. "Category". */
  nameHeading: string;
  rows: RankedRow[];
  total: number;
  extraHeading?: string;
  selected: string | null;
  onSelect: (value: string | null) => void;
}

/** "Top ..." as a table, biggest first: the number, its share as a bar, and optionally one more figure. Selecting
 *  a name filters the dashboard to it; again clears it. */
export function RankedTable({ title, nameHeading, rows, total, extraHeading, selected, onSelect }: RankedTableProps) {
  const max = Math.max(...rows.map((r) => r.n), 1);
  return (
    <article className={styles.panel} aria-label={title}>
      <h2 className={styles.panelTitle}>{title}</h2>
      {rows.length === 0 ? (
        <p className={styles.empty}>No cases.</p>
      ) : (
        <div className={styles.rankedFrame}>
          <table className={styles.ranked}>
            <caption className="visually-hidden">{title}, biggest first. Select a name to filter by it.</caption>
            <thead>
              <tr>
                <th scope="col">{nameHeading}</th>
                <th scope="col" className={styles.number}>Cases</th>
                {extraHeading && <th scope="col" className={styles.number}>{extraHeading}</th>}
                <th scope="col" className={styles.barCol}><span className="visually-hidden">Share</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const on = selected === r.value;
                const share = total ? Math.round((r.n / total) * 100) : 0;
                return (
                  <tr key={r.value} data-selected={on || undefined}>
                    <th scope="row">
                      <button type="button" className={styles.nameButton} aria-pressed={on}
                        title={on ? 'Show every value again' : `Show only ${r.label}`}
                        onClick={() => onSelect(on ? null : r.value)}>
                        {r.label}
                      </button>
                    </th>
                    <td className={styles.number}><strong>{r.n.toLocaleString('en-MY')}</strong></td>
                    {extraHeading && <td className={styles.number}>{r.extra}</td>}
                    <td className={styles.barCol}>
                      <span className={styles.shareBar}>
                        <span className={styles.track} aria-hidden>
                          <span className={styles.fill} style={{ width: `${(r.n / max) * 100}%` }} />
                        </span>
                        <span className={styles.shareText}>{share}%</span>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}
