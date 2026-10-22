import { clsx } from 'clsx';
import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import styles from './Badge.module.css';

export type Tone = 'success' | 'error' | 'warning' | 'info' | 'neutral' | 'accent';

/** A tinted pill. Status is never colour alone: pass an icon, and the text always carries the meaning. */
export function Badge({ tone, icon: Icon, children }: { tone: Tone; icon?: LucideIcon; children: ReactNode }) {
  return (
    <span className={clsx(styles.badge, styles[tone])}>
      {Icon && <Icon aria-hidden />}
      {children}
    </span>
  );
}
