import { clsx } from 'clsx';
import { CircleCheck, Info, OctagonAlert, TriangleAlert, X } from 'lucide-react';
import type { ReactNode } from 'react';

import styles from './Alert.module.css';

export type AlertTone = 'success' | 'error' | 'warning' | 'info';

const ICONS = { success: CircleCheck, error: OctagonAlert, warning: TriangleAlert, info: Info };

interface AlertProps {
  tone: AlertTone;
  children: ReactNode;
  items?: string[];
  onDismiss?: () => void;
}

/** A message in the status palette, always icon plus text. Errors are announced at once (role="alert"). */
export function Alert({ tone, children, items, onDismiss }: AlertProps) {
  const Icon = ICONS[tone];
  return (
    <div className={clsx(styles.alert, styles[tone])} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon className={styles.icon} aria-hidden />
      <div className={styles.body}>
        <p>{children}</p>
        {items && items.length > 0 && (
          <ul>
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
      </div>
      {onDismiss && (
        <button type="button" className={styles.dismiss} onClick={onDismiss} aria-label="Dismiss message">
          <X aria-hidden />
        </button>
      )}
    </div>
  );
}
