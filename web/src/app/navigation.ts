import {
  CheckCheck,
  FolderOpen,
  Hourglass,
  Inbox,
  ListChecks,
  MessagesSquare,
  ReceiptText,
  Shield,
  SquarePen,
  UserRound,
  type LucideIcon,
} from 'lucide-react';

import type { Role } from '@/features/auth/types';

export type PageKey =
  | 'approval' | 'fraud' | 'awaiting' | 'resolved' | 'cases' | 'intake' | 'myCases' | 'newComplaint'
  | 'profile' | 'transactions';
/** 'Account' pages open from the account menu at the bottom of the sidebar, not from the page list. */
export type Section = 'Queues' | 'Records' | 'Intake' | 'My bank' | 'Account';

export interface PageDef {
  key: PageKey;
  title: string;
  path: string;
  icon: LucideIcon;
  section: Section;
}

export const PAGE_DEFS: Record<PageKey, PageDef> = {
  approval: { key: 'approval', title: 'Approval queue', path: '/approval', icon: ListChecks, section: 'Queues' },
  fraud: { key: 'fraud', title: 'Fraud queue', path: '/fraud', icon: Shield, section: 'Queues' },
  awaiting: { key: 'awaiting', title: 'Awaiting customer', path: '/awaiting', icon: Hourglass, section: 'Queues' },
  resolved: { key: 'resolved', title: 'Resolved automatically', path: '/resolved', icon: CheckCheck, section: 'Records' },
  cases: { key: 'cases', title: 'All cases', path: '/cases', icon: FolderOpen, section: 'Records' },
  intake: { key: 'intake', title: 'Submit complaint', path: '/intake', icon: Inbox, section: 'Intake' },
  myCases: { key: 'myCases', title: 'My cases', path: '/my-cases', icon: MessagesSquare, section: 'My bank' },
  newComplaint: { key: 'newComplaint', title: 'New complaint', path: '/new-complaint', icon: SquarePen, section: 'My bank' },
  profile: { key: 'profile', title: 'Profile', path: '/profile', icon: UserRound, section: 'Account' },
  transactions: { key: 'transactions', title: 'Transactions', path: '/transactions', icon: ReceiptText, section: 'Account' },
};

/** Each role sees exactly these pages; the first is where it lands after signing in. */
export const PAGES_BY_ROLE: Record<Role, PageKey[]> = {
  officer: ['approval', 'cases', 'intake'],
  fraud: ['fraud', 'cases', 'intake'],
  manager: ['approval', 'fraud', 'awaiting', 'resolved', 'cases', 'intake'],
  customer: ['myCases', 'newComplaint', 'profile', 'transactions'],
};

/** The sections of the sidebar's page list, in order ('Account' is left out: see AccountMenu). */
export const SECTIONS: Section[] = ['Queues', 'Records', 'Intake', 'My bank'];

export const pagesFor = (role: Role): PageDef[] => PAGES_BY_ROLE[role].map((key) => PAGE_DEFS[key]);
export const homePath = (role: Role): string => PAGE_DEFS[PAGES_BY_ROLE[role][0]].path;
export const canOpen = (role: Role, page: PageKey): boolean => PAGES_BY_ROLE[role].includes(page);
