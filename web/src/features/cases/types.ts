/** Case shapes as the API returns them (app/api.py, app/store.py). */

export type CaseStatus =
  | 'AWAITING_CUSTOMER'
  | 'PENDING_APPROVAL'
  | 'FRAUD_QUEUE'
  | 'RESOLVED'
  | 'ANSWERED'
  | 'APPROVED'
  | 'REJECTED'
  | 'SENT';

/** One row of GET /cases for staff: the case's columns without the full record. */
export interface CaseRow {
  complaint_id: string;
  customer_id: string;
  received_at: string;
  channel: string;
  text: string;
  category: string | null;
  matched_txn_id: string | null;
  outcome: string | null;
  refund_amount_myr: number | null;
  priority: string | null;
  reply_language: string | null;
  route: string | null;
  status: CaseStatus;
  reply_text: string;
  check_ok: number;
  flags: string;
  sla_due: string | null;
  created_at: string;
  updated_at: string;
  flagged: boolean;
  /** Who last approved, rejected or sent the holding reply; null until a person acts. */
  handled_by?: string | null;
}

export interface AuditEntry {
  ts: string;
  actor: string;
  action: string;
  detail: string;
}

/** GET /audit (manager only): every case's audit log, newest first, plus the people and actions for the filters. */
export interface AuditLog {
  entries: (AuditEntry & { id: number; complaint_id: string })[];
  actors: string[];
  actions: string[];
}

export interface AuditFilters {
  actor?: string;
  action?: string;
  case?: string;
  peopleOnly?: boolean;
}

/** The at-a-glance view from agent/summary.py. */
export interface CaseSummary {
  headline: string;
  why_here: string[];
  story: string;
  decision: string;
  key_row: string;
  warnings: string[];
  tone: 'warning' | 'error' | 'info' | 'success';
}

export interface ReplyEvidence {
  source?: string;
  language?: string;
  language_why?: string;
  rejected_drafts?: { source: string; text: string; problems: string[] }[];
}

/** The stored CaseRecord; only the parts the screen reads are typed. */
export interface CaseRecord {
  complaint: { channel: string; received_at: string; subject?: string; text: string };
  extraction: Record<string, unknown> & { source?: string };
  decision: {
    reasons?: string[];
    evidence?: Record<string, unknown> & { reply?: ReplyEvidence; fee_due?: number | null };
  };
  trace?: { step: string; ms: number }[];
  llm_usage?: { calls?: number; input_tokens?: number; output_tokens?: number; failures?: string[] };
}

/** GET /cases/{id} for staff. */
export interface CaseDetail extends Omit<CaseRow, 'flagged'> {
  record: CaseRecord;
  audit: AuditEntry[];
  summary: CaseSummary;
}

export interface CustomerMessage {
  ts: string;
  from: 'customer' | 'bank';
  text: string;
}

/** What a customer sees of their own case (roles.customer_view): never an unsent draft or the decision internals. */
export interface CustomerCase {
  complaint_id: string;
  received_at: string;
  channel: string;
  text: string;
  status: CaseStatus;
  updated_at: string;
  messages?: CustomerMessage[];
}

export interface IntakeComplaint {
  complaint_id?: string;
  customer_id: string;
  channel: string;
  received_at: string;
  subject: string;
  text: string;
}
