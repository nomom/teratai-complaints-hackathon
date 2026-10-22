import * as RadixTabs from '@radix-ui/react-tabs';
import type { ReactNode } from 'react';

import styles from './Tabs.module.css';

export interface TabItem {
  value: string;
  label: string;
  content: ReactNode;
}

/** Tabs with arrow-key movement between triggers (Radix). The first tab opens by default. */
export function Tabs({ items, label, defaultValue }: { items: TabItem[]; label: string; defaultValue?: string }) {
  return (
    <RadixTabs.Root className={styles.root} defaultValue={defaultValue ?? items[0]?.value}>
      <RadixTabs.List className={styles.list} aria-label={label}>
        {items.map((item) => (
          <RadixTabs.Trigger key={item.value} value={item.value} className={styles.trigger}>
            {item.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((item) => (
        <RadixTabs.Content key={item.value} value={item.value} className={styles.content}>
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
