import { clsx } from 'clsx';

import type { CustomerCase } from '@/features/cases/types';

import styles from './customer.module.css';

/** The customer's complaint, then every message actually exchanged, oldest first. */
export function Thread({ caseItem }: { caseItem: CustomerCase }) {
  const items = [
    { from: 'customer' as const, ts: caseItem.received_at, text: caseItem.text },
    ...(caseItem.messages ?? []),
  ];
  return (
    <ol className={styles.thread} aria-label="Conversation">
      {items.map((m, i) => (
        <li key={i} className={clsx(styles.message, m.from === 'customer' && styles.mine)}>
          <p className={styles.who}>
            {m.from === 'customer' ? 'You' : 'Teratai Bank'} · {m.ts}
          </p>
          <p className={styles.text}>{m.text}</p>
        </li>
      ))}
    </ol>
  );
}
