import type { CaseStatus } from '../types';
import { AUTO_SENT } from './status';

/** The four queue pages share one component; this is what differs between them. */
export interface QueueConfig {
  title: string;
  statuses: CaseStatus[];
  subtitle: string;
  empty: string;
  actions?: boolean;
  flagFilter?: boolean;
}

export const QUEUES = {
  approval: {
    title: 'Approval queue',
    statuses: ['PENDING_APPROVAL'],
    subtitle: 'Each case says why it needs you. Review the decision and the reply, then approve or reject.',
    empty: 'New cases appear here as the agent routes them to a person.',
    actions: true,
  },
  fraud: {
    title: 'Fraud queue',
    statuses: ['FRAUD_QUEUE'],
    subtitle: 'Possible fraud and scams the agent handed to the fraud team.',
    empty: 'New cases appear here as the agent routes them to the fraud team.',
    actions: true,
  },
  awaiting: {
    title: 'Awaiting customer',
    statuses: ['AWAITING_CUSTOMER'],
    subtitle: 'Open cases with no decision yet: we asked these customers for more details. Their reply continues the case.',
    empty: 'No customer owes us an answer right now.',
  },
  resolved: {
    title: 'Resolved automatically',
    statuses: AUTO_SENT,
    subtitle: 'Replies that went out with no person involved. Spot-check them; flag anything that looks wrong.',
    empty: "The agent hasn't resolved any case on its own yet.",
    flagFilter: true,
  },
} satisfies Record<string, QueueConfig>;
