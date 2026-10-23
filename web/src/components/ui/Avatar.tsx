import { clsx } from 'clsx';

import { initials } from '@/lib/format';

import styles from './Avatar.module.css';

/** The person's initials in a tinted circle. Decorative: the name is always written next to it. */
export function Avatar({ name, size = 'sm' }: { name: string; size?: 'sm' | 'lg' }) {
  return (
    <span className={clsx(styles.avatar, styles[size])} aria-hidden>
      {initials(name)}
    </span>
  );
}
