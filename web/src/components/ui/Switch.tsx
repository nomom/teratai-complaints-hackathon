import * as RadixSwitch from '@radix-ui/react-switch';
import type { LucideIcon } from 'lucide-react';
import { useId } from 'react';

import styles from './Switch.module.css';

interface SwitchProps {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  icon?: LucideIcon;
}

export function Switch({ label, checked, onCheckedChange, icon: Icon }: SwitchProps) {
  const id = useId();
  return (
    <div className={styles.row}>
      <RadixSwitch.Root id={id} className={styles.track} checked={checked} onCheckedChange={onCheckedChange}>
        <RadixSwitch.Thumb className={styles.thumb} />
      </RadixSwitch.Root>
      <label htmlFor={id} className={styles.label}>
        {Icon && <Icon aria-hidden />}
        {label}
      </label>
    </div>
  );
}
