import {
  ArrowUp,
  Check,
  ChevronsUp,
  ChevronUp,
  CircleHelp,
  Clock,
  Flag,
  Hourglass,
  Minus,
  Reply,
  X,
  type LucideIcon,
} from 'lucide-react';

import type { Tone } from '@/components/ui';

import type { CaseStatus } from '../types';

interface StatusStyle {
  label: string;
  tone: Tone;
  icon: LucideIcon;
}

/** How staff read each status. */
export const STATUS: Record<CaseStatus, StatusStyle> = {
  PENDING_APPROVAL: { label: 'Approval queue', tone: 'warning', icon: Hourglass },
  FRAUD_QUEUE: { label: 'Fraud queue', tone: 'error', icon: Flag },
  AWAITING_CUSTOMER: { label: 'Awaiting customer', tone: 'info', icon: CircleHelp },
  RESOLVED: { label: 'Resolved automatically', tone: 'success', icon: Check },
  ANSWERED: { label: 'Answered (off-topic)', tone: 'neutral', icon: Reply },
  APPROVED: { label: 'Approved and sent', tone: 'success', icon: Check },
  REJECTED: { label: 'Rejected', tone: 'neutral', icon: X },
  SENT: { label: 'Resolved automatically (old)', tone: 'success', icon: Check },
};

/** What a customer is told. Both queues read the same: a customer is never told their case is with fraud. */
export const CUSTOMER_STATUS: Record<CaseStatus, StatusStyle> = {
  AWAITING_CUSTOMER: { label: 'We need more details from you', tone: 'info', icon: CircleHelp },
  PENDING_APPROVAL: { label: 'Being reviewed', tone: 'warning', icon: Hourglass },
  FRAUD_QUEUE: { label: 'Being reviewed', tone: 'warning', icon: Hourglass },
  RESOLVED: { label: 'Answered', tone: 'success', icon: Check },
  ANSWERED: { label: 'Answered', tone: 'success', icon: Check },
  APPROVED: { label: 'Answered', tone: 'success', icon: Check },
  SENT: { label: 'Answered', tone: 'success', icon: Check },
  REJECTED: { label: 'Closed', tone: 'neutral', icon: X },
};

export const PRIORITY: Record<string, StatusStyle> = {
  P1: { label: 'P1 urgent', tone: 'error', icon: ChevronsUp },
  P2: { label: 'P2', tone: 'warning', icon: ChevronUp },
  P3: { label: 'P3', tone: 'neutral', icon: Minus },
};

export const SLA_ICON = Clock;
export const ESCALATE_ICON = ArrowUp;

/** Waiting for a person: approve or reject happens here. */
export const QUEUE_STATUSES: CaseStatus[] = ['PENDING_APPROVAL', 'FRAUD_QUEUE'];
/** Replies that went out with no person involved. */
export const AUTO_SENT: CaseStatus[] = ['RESOLVED', 'ANSWERED', 'SENT'];
/** The reply has gone out to the customer. */
export const SENT_STATUSES: CaseStatus[] = ['RESOLVED', 'ANSWERED', 'APPROVED', 'SENT'];
/** Statuses offered by the All cases filter, in this order. */
export const FILTER_STATUSES: CaseStatus[] = [
  'PENDING_APPROVAL', 'FRAUD_QUEUE', 'AWAITING_CUSTOMER', 'RESOLVED', 'ANSWERED', 'APPROVED', 'REJECTED',
];
