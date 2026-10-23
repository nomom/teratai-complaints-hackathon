import { clsx } from 'clsx';

import styles from './OrbMark.module.css';

/** Teratai Bank's mark: a jade orb. Decorative; the bank's name always sits next to it. */
export function OrbMark({ size = 20, className }: { size?: number; className?: string }) {
  return <span className={clsx(styles.orb, className)} style={{ width: size, height: size }} aria-hidden />;
}
