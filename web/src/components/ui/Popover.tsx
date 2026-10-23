import * as RadixPopover from '@radix-ui/react-popover';
import { clsx } from 'clsx';
import type { ReactNode } from 'react';

import styles from './Popover.module.css';

interface PopoverProps {
  trigger: ReactNode;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Which side of the trigger it opens on; it flips by itself when there is no room. */
  side?: 'top' | 'bottom';
  className?: string;
}

/** A panel anchored to its trigger; Escape and clicking outside close it, and focus returns to the trigger. */
export function Popover({ trigger, children, open, onOpenChange, side = 'bottom', className }: PopoverProps) {
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content className={clsx(styles.content, className)} sideOffset={8} side={side} align="start">
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
