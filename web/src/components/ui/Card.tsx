import { clsx } from 'clsx';
import type { ReactNode } from 'react';

import styles from './Card.module.css';

export function Card({ title, children, className }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={clsx(styles.card, className)}>
      {title && <h3 className={styles.title}>{title}</h3>}
      {children}
    </section>
  );
}

/** A small labelled value, laid out in a responsive grid by TileGrid. */
export function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={clsx(styles.card, styles.tile)}>
      <p className={styles.label}>{label}</p>
      <p className={styles.value}>{children}</p>
    </div>
  );
}

export function TileGrid({ children }: { children: ReactNode }) {
  return <div className={styles.grid}>{children}</div>;
}
