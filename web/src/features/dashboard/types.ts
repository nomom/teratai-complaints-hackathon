/** GET /dashboard (app/dashboard.py): the numbers behind the Dashboard page, only over the viewer's own cases. */

import type { CaseStatus } from '@/features/cases/types';

/** The columns the dashboard counts by and filters on. `language` is the case's reply_language. */
export type Dimension = 'status' | 'route' | 'category' | 'outcome' | 'priority' | 'channel' | 'language';

/** An empty column (e.g. the outcome of a case still waiting for the customer); also a filter value. */
export const NONE = 'NONE';

export interface DashboardKpis {
  /** Waiting for a person to approve or reject (approval and fraud queues). */
  waiting: number;
  awaiting_customer: number;
  /** The reply went out with no person involved. */
  auto_sent: number;
  /** Still with the bank or the customer: approval queue, fraud queue, awaiting customer. */
  open: number;
  /** Open and past the time allowed to acknowledge the customer. */
  overdue: number;
  refund_sent_myr: number;
  refund_waiting_myr: number;
}

/** One day of complaints received, with the same figures as the headline. */
export interface DailyKpis extends DashboardKpis {
  day: string;
  received: number;
}

export interface CategoryRow {
  category: string;
  n: number;
  refund_sent_myr: number;
  /** outcome -> number of cases (NONE: not decided yet). */
  outcomes: Record<string, number>;
}

export interface PersonActions {
  actor: string;
  name: string;
  approve: number;
  edit_approve: number;
  reject: number;
  holding_reply: number;
}

export interface Dashboard {
  total: number;
  kpis: DashboardKpis;
  /** The same figures for the period just before, as long as this one; null for "all dates". */
  previous: { date_from: string; date_to: string; total: number; kpis: DashboardKpis } | null;
  /** Days with complaints only, oldest first. */
  daily: DailyKpis[];
  by_day: { day: string; status: CaseStatus; n: number }[];
  /** Biggest first. */
  categories: CategoryRow[];
  /** value -> number of cases, biggest first. */
  breakdowns: Record<Dimension, Record<string, number>>;
  /** Every value each filter can take, from all the viewer's cases (not narrowed by the filters). */
  options: Record<Dimension, string[]>;
  /** The first and last day received, over every case the viewer may see. */
  date_range: { first: string | null; last: string | null };
  /** The dates the numbers cover (a preset worked out by the API); null at an open end. */
  applied: { date_from: string | null; date_to: string | null };
  /** Manager only: who approved, rejected or sent a holding reply on these cases. */
  people: PersonActions[] | null;
}
