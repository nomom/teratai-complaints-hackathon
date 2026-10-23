import { OUTCOME_COLOR, OUTCOME_ORDER } from '../lib/kpi';
import { valueLabel } from '../lib/series';
import type { CategoryRow } from '../types';
import styles from './charts.module.css';

/**
 * How each category ends: one bar per category, split by outcome as a share of its cases, biggest category first.
 * The legend names every colour; hover a segment for its number; the table under it holds every number.
 */
export function OutcomeByCategory({ categories }: { categories: CategoryRow[] }) {
  const outcomes = OUTCOME_ORDER.filter((o) => categories.some((c) => c.outcomes[o]));

  return (
    <article className={styles.panel} aria-label="Outcomes by category">
      <h2 className={styles.panelTitle}>Outcomes by category</h2>
      <p className={styles.panelNote}>What the agent decided for each kind of complaint, as a share of its cases.</p>
      <ul className={styles.legend} aria-label="Outcome">
        {outcomes.map((o) => (
          <li key={o}>
            <span className={styles.swatch} style={{ background: OUTCOME_COLOR[o] }} aria-hidden />
            {valueLabel('outcome', o)}
          </li>
        ))}
      </ul>
      <div className={styles.stackRows} aria-hidden>
        {categories.map((c) => (
          <div key={c.category} className={styles.stackRow}>
            <span className={styles.stackName}>{valueLabel('category', c.category)}</span>
            <span className={styles.stackBar}>
              {outcomes.filter((o) => c.outcomes[o]).map((o) => (
                <span key={o} className={styles.stackPart}
                  style={{ flexGrow: c.outcomes[o], background: OUTCOME_COLOR[o] }}
                  title={`${valueLabel('category', c.category)}, ${valueLabel('outcome', o)}: ${c.outcomes[o]} of ${c.n}`} />
              ))}
            </span>
            <span className={styles.stackTotal}>{c.n.toLocaleString('en-MY')}</span>
          </div>
        ))}
      </div>
      <details className={styles.tableToggle}>
        <summary>Show as table</summary>
        <div className={styles.tableFrame}>
          <table className={styles.table}>
            <caption className="visually-hidden">Outcomes by category</caption>
            <thead>
              <tr>
                <th scope="col">Category</th>
                {outcomes.map((o) => <th key={o} scope="col" className={styles.number}>{valueLabel('outcome', o)}</th>)}
                <th scope="col" className={styles.number}>Total</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.category}>
                  <th scope="row">{valueLabel('category', c.category)}</th>
                  {outcomes.map((o) => <td key={o} className={styles.number}>{c.outcomes[o] ?? 0}</td>)}
                  <td className={styles.number}>{c.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </article>
  );
}
