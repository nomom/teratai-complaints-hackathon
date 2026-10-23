import { apiRequest } from '@/lib/apiClient';

import type { AuditFilters, AuditLog, CaseDetail, CaseRow, CaseStatus, CustomerCase, IntakeComplaint } from './types';

const EVERY = 100000;

export const listCases = (statuses?: CaseStatus[]) => {
  const query = new URLSearchParams({ limit: String(EVERY) });
  if (statuses?.length) query.set('status', statuses.join(','));
  return apiRequest<CaseRow[]>(`/cases?${query}`);
};

export const listOwnCases = () => apiRequest<CustomerCase[]>(`/cases?limit=${EVERY}`);

export const getCase = (id: string) => apiRequest<CaseDetail>(`/cases/${encodeURIComponent(id)}`);
export const getOwnCase = (id: string) => apiRequest<CustomerCase>(`/cases/${encodeURIComponent(id)}`);

export const getCounts = () => apiRequest<Partial<Record<CaseStatus, number>>>('/cases/counts');

/** replyText null sends the agent's draft as it is; an edited reply is self-checked again before it goes out.
 *  `note` is the officer's reason, stored with the action (required by the screen when the reply was edited). */
export const approveCase = (id: string, replyText: string | null, note = '') =>
  apiRequest<CaseDetail>(`/cases/${encodeURIComponent(id)}/approve`, {
    method: 'POST', body: { reply_text: replyText, note },
  });

/** Nothing is sent; `note` is why, stored with the action. */
export const rejectCase = (id: string, note: string) =>
  apiRequest<CaseDetail>(`/cases/${encodeURIComponent(id)}/reject`, { method: 'POST', body: { note } });

/** The fraud team's holding reply: self-checked, sent once, and the case stays in the fraud queue. */
export const sendHoldingReply = (id: string, replyText: string | null) =>
  apiRequest<CaseDetail>(`/cases/${encodeURIComponent(id)}/holding-reply`, {
    method: 'POST', body: { reply_text: replyText },
  });

/** The manager's audit log across every case. */
export const listAudit = (filters: AuditFilters) => {
  const query = new URLSearchParams({ limit: '500' });
  if (filters.actor) query.set('actor', filters.actor);
  if (filters.action) query.set('action', filters.action);
  if (filters.case?.trim()) query.set('case', filters.case.trim());
  if (filters.peopleOnly) query.set('people_only', 'true');
  return apiRequest<AuditLog>(`/audit?${query}`);
};

export const flagCase = (id: string, note: string) =>
  apiRequest<CaseDetail>(`/cases/${encodeURIComponent(id)}/flag`, { method: 'POST', body: { note } });

/** Staff intake for any customer (call-centre note, live-round row). */
export const submitComplaint = (complaint: IntakeComplaint) =>
  apiRequest<{ complaint_id: string }>('/complaints', { method: 'POST', body: complaint });

/** A signed-in customer files under their own ID, from the app. */
export const fileOwnComplaint = (text: string, subject: string) =>
  apiRequest<{ complaint_id: string }>('/me/complaints', { method: 'POST', body: { text, subject } });

/** The answer to the bank's follow-up question; the worker reprocesses the case. */
export const sendCustomerReply = (id: string, text: string) =>
  apiRequest<{ message_id: string }>(`/cases/${encodeURIComponent(id)}/messages`, { method: 'POST', body: { text } });
