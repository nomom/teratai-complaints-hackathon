import { Card } from '@/components/ui';

import type { PersonActions } from '../types';
import styles from './charts.module.css';

const ACTIONS: { key: keyof Omit<PersonActions, 'actor' | 'name'>; label: string }[] = [
  { key: 'approve', label: 'Approved as drafted' },
  { key: 'edit_approve', label: 'Edited and approved' },
  { key: 'reject', label: 'Rejected' },
  { key: 'holding_reply', label: 'Holding replies' },
];

const totalOf = (p: PersonActions) => ACTIONS.reduce((sum, a) => sum + p[a.key], 0);

/** Manager only: who approved, rejected or sent a fraud holding reply on the cases in view (from the audit log). */
export function PeopleCard({ people }: { people: PersonActions[] }) {
  const max = Math.max(...people.map(totalOf), 1);
  return (
    <Card title="Actions by person" className={styles.people}>
      <p className={styles.muted}>Every approve, reject and holding reply on the cases above, from the audit log.</p>
      {people.length === 0 ? (
        <p className={styles.empty}>Nobody has acted on these cases yet.</p>
      ) : (
        <div className={styles.tableFrame}>
          <table className={styles.table}>
            <caption className="visually-hidden">Actions by person</caption>
            <thead>
              <tr>
                <th scope="col">Person</th>
                {ACTIONS.map((a) => <th key={a.key} scope="col" className={styles.number}>{a.label}</th>)}
                <th scope="col" className={styles.number}>Total</th>
                <th scope="col"><span className="visually-hidden">Share of the busiest person</span></th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.actor}>
                  <th scope="row">
                    {p.name}
                    {p.name !== p.actor && <span className={styles.username}>{p.actor}</span>}
                  </th>
                  {ACTIONS.map((a) => <td key={a.key} className={styles.number}>{p[a.key]}</td>)}
                  <td className={styles.number}><strong>{totalOf(p)}</strong></td>
                  <td className={styles.meterCell} aria-hidden>
                    <span className={styles.track}>
                      <span className={styles.fill} style={{ width: `${(totalOf(p) / max) * 100}%` }} />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
