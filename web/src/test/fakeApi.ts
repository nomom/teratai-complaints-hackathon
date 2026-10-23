/**
 * An in-memory stand-in for app/api.py, with the same role rules: officer sees the HUMAN_APPROVAL route, fraud the
 * FRAUD_TEAM route, manager everything, a customer only their own cases (and never an unsent draft).
 * install() replaces fetch; every test gets a fresh copy of the seed data.
 */
import { vi } from 'vitest';

import type { CaseDetail, CaseRow, CaseStatus } from '@/features/cases/types';
import type { Profile, Statement, Transaction } from '@/features/customer/types';

type Role = 'officer' | 'fraud' | 'manager' | 'customer';
interface Account { password: string; role: Role; full_name: string }

const STAFF: Record<string, Account> = {
  officer1: { password: '1234', role: 'officer', full_name: 'Aisyah binti Rahman' },
  fraud1: { password: '1234', role: 'fraud', full_name: 'Daniel Lim Wei Jie' },
  manager1: { password: '1234', role: 'manager', full_name: 'Priya Nair' },
};
const CUSTOMERS: Record<string, string> = { 'CUS-00150': 'Ravi a/l Rajan', 'CUS-02394': 'Nur Aina', 'CUS-00996': 'Nur Sofea' };

const NOW = '2026-10-22 10:00:00';

export function makeCase(id: string, over: Partial<CaseDetail>): CaseDetail {
  return {
    complaint_id: id, customer_id: 'CUS-00150', received_at: '2026-09-29 10:00', channel: 'App chat',
    text: `Complaint text of ${id}`, category: 'FAILED_TRANSFER', matched_txn_id: 'TXN-0000001', outcome: 'REFUND',
    refund_amount_myr: 100, priority: 'P2', reply_language: 'EN', route: 'HUMAN_APPROVAL', status: 'PENDING_APPROVAL',
    reply_text: `Draft reply for ${id}`, check_ok: 1, flags: '[]', sla_due: '2026-09-30 10:00', created_at: NOW,
    updated_at: NOW,
    record: { complaint: { channel: 'App chat', received_at: '2026-09-29 10:00', text: `Complaint text of ${id}` },
      extraction: { source: 'rules', category: 'FAILED_TRANSFER' }, decision: { reasons: ['Reason one'], evidence: {} },
      trace: [{ step: 'extract', ms: 3 }], llm_usage: { calls: 0 } },
    audit: [{ ts: NOW, actor: 'agent', action: 'decided', detail: '{}' }],
    summary: { headline: `${id} headline`, why_here: [`Why ${id} is here`], story: `Story of ${id}`, decision: 'Refund',
      key_row: 'TXN-0000001 | RM100.00', warnings: [], tone: 'warning' },
    ...over,
  };
}

export function seedCases(): CaseDetail[] {
  return [
    makeCase('CMP-P3', { priority: 'P3', updated_at: '2026-10-22 11:00:00' }),           // newest, lower priority
    makeCase('CMP-P1', { priority: 'P1', customer_id: 'CUS-02394', updated_at: '2026-10-22 09:00:00' }),
    makeCase('CMP-FRAUD', { route: 'FRAUD_TEAM', status: 'FRAUD_QUEUE', outcome: 'INVESTIGATE', priority: 'P1' }),
    makeCase('CMP-AUTO', { route: 'AUTO_RESOLVE', status: 'RESOLVED',
      audit: [{ ts: NOW, actor: 'agent', action: 'reply_sent', detail: 'Your refund is on its way.' }] }),
  ];
}

const HUMAN: Record<string, string> = { officer: 'HUMAN_APPROVAL', fraud: 'FRAUD_TEAM' };

/** GET /me/profile for any signed-in customer: their own ID and name, the same two accounts. */
const profileOf = (customerId: string, fullName: string): Profile => ({
  customer_id: customerId, full_name: fullName, date_of_birth: '1990-05-14', state: 'Selangor', city: 'Shah Alam',
  segment: 'Retail', preferred_language: 'EN', email: 'customer@example.com', customer_since: '2015-03-02',
  accounts: [
    { account_id: 'ACC-000300', product: 'Savings Plus', open_date: '2015-03-02', status: 'Active', card_last4: '4821' },
    { account_id: 'ACC-000301', product: 'Credit Card Classic', open_date: '2023-01-19', status: 'Active', card_last4: '1907' },
  ],
});

const txn = (over: Partial<Transaction>): Transaction => ({
  txn_id: 'TXN-0000000', txn_time: '2026-09-29 14:16:08', account_id: 'ACC-000300', direction: 'DR', amount_myr: 10,
  channel: 'Card POS', merchant_or_counterparty: 'Shop', counterparty_bank: '', card_last4: '4821', status: 'Completed',
  description: '', reportable: true, ...over,
});

/** GET /me/transactions, newest first: a card charge, a transfer in, a failed online charge, and an old ATM withdrawal. */
export const STATEMENT: Statement = {
  as_of: '2026-09-30 18:00',
  report_window_days: 45,
  transactions: [
    txn({ txn_id: 'TXN-0000101', txn_time: '2026-09-29 14:16:08', merchant_or_counterparty: 'FoodKu', amount_myr: 12.45,
      channel: 'Card e-Commerce' }),
    txn({ txn_id: 'TXN-0000102', txn_time: '2026-09-20 10:19:17', direction: 'CR', amount_myr: 250,
      channel: 'DuitNow Received', merchant_or_counterparty: 'Siti Aminah', card_last4: '' }),
    txn({ txn_id: 'TXN-0000103', txn_time: '2026-08-30 20:17:33', account_id: 'ACC-000301', amount_myr: 101.43,
      channel: 'Card e-Commerce', merchant_or_counterparty: 'ShopLah Online', card_last4: '1907', status: 'Failed' }),
    txn({ txn_id: 'TXN-0000104', txn_time: '2026-07-02 19:30:02', amount_myr: 200, channel: 'ATM Withdrawal',
      merchant_or_counterparty: 'Shah Alam Branch', description: 'ATM-SHA-01', reportable: false }),
  ],
};

export function installFakeApi(cases: CaseDetail[] = seedCases()) {
  const tokens = new Map<string, string>();
  const signedUp = new Map<string, string>();
  const calls: { method: string; path: string; body: unknown }[] = [];

  const account = (username: string): (Account & { username: string }) | null => {
    if (STAFF[username]) return { ...STAFF[username], username };
    const id = username.toUpperCase();
    return CUSTOMERS[id] ? { username: id, role: 'customer', full_name: CUSTOMERS[id], password: signedUp.get(id) ?? '' } : null;
  };
  const visible = (who: Account & { username: string }, c: CaseDetail) =>
    who.role === 'manager' || (who.role === 'customer' ? c.customer_id === who.username : c.route === HUMAN[who.role]);
  const customerView = (c: CaseDetail) => ({
    complaint_id: c.complaint_id, received_at: c.received_at, channel: c.channel, text: c.text, status: c.status,
    updated_at: c.updated_at,
    messages: c.audit.filter((a) => ['question_sent', 'reply_sent', 'customer_replied'].includes(a.action))
      .map((a) => ({ ts: a.ts, from: a.action === 'customer_replied' ? 'customer' : 'bank', text: a.detail })),
  });
  const row = (c: CaseDetail): CaseRow => {
    const columns = Object.fromEntries(Object.entries(c).filter(([k]) => !['record', 'audit', 'summary'].includes(k)));
    const handled = c.audit.findLast((a) => a.action === 'human_action' || a.action === 'holding_reply_sent');
    return { ...(columns as Omit<CaseRow, 'flagged'>), flagged: c.audit.some((a) => a.action === 'flagged_for_review'),
      handled_by: handled?.actor ?? null };
  };
  const act = (c: CaseDetail, actor: string, action: string, detail: string) =>
    c.audit.push({ ts: NOW, actor, action, detail });
  const json = (status: number, body: unknown) =>
    Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
  const fail = (status: number, detail: unknown) => json(status, { detail });

  const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost');
    const path = url.pathname.replace(/^\/api/, '');
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    // Tokens are "token-<username>", issued by login or preset by renderApp; a customer must have signed up
    const token = (init?.headers as Record<string, string> | undefined)?.Authorization?.replace('Bearer ', '');
    const holder = token?.startsWith('token-') ? account(tokens.get(token) ?? token.slice('token-'.length)) : null;
    const who = holder && (holder.role !== 'customer' || holder.password) ? holder : null;

    if (path === '/auth/login') {
      const a = account(body.username);
      if (a?.role === 'customer' && !a.password) return fail(403, { code: 'NOT_SIGNED_UP', message: "You haven't signed up yet. Please sign up first, then log in." });
      if (!a || a.password !== body.password) return fail(401, { code: 'INVALID_CREDENTIALS', message: 'Wrong username or password.' });
      const t = `token-${a.username}`;
      tokens.set(t, a.username);
      return json(200, { access_token: t, token_type: 'bearer', expires_in: 28800,
        user: { username: a.username, role: a.role, full_name: a.full_name, approval_limit_myr: null } });
    }
    if (path === '/auth/signup/verify' || path === '/auth/signup') {
      const id = String(body.customer_id).trim().toUpperCase();
      if (!CUSTOMERS[id]) return fail(404, { code: 'NOT_A_CUSTOMER', message: `${id} is not a Teratai Bank customer. Check your customer ID and try again.` });
      if (signedUp.has(id)) return fail(409, { code: 'ALREADY_SIGNED_UP', message: 'This customer ID has already signed up. Please log in instead.' });
      if (path === '/auth/signup') signedUp.set(id, body.password);
      return json(path === '/auth/signup' ? 201 : 200, { customer_id: id });
    }
    if (!who) return fail(401, { code: 'INVALID_TOKEN', message: 'Your session is not valid. Please log in again.' });
    if (path === '/auth/me') return json(200, { username: who.username, role: who.role, full_name: who.full_name, approval_limit_myr: null });

    if (path === '/me/profile' || path === '/me/transactions') {
      if (who.role !== 'customer') return fail(403, { code: 'FORBIDDEN', message: `Your role (${who.role}) cannot do this.` });
      return json(200, path === '/me/profile' ? profileOf(who.username, who.full_name) : STATEMENT);
    }

    if (path === '/cases' && method === 'GET') {
      const statuses = url.searchParams.get('status')?.split(',') as CaseStatus[] | undefined;
      const rows = cases.filter((c) => visible(who, c) && (!statuses || statuses.includes(c.status)))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
      return json(200, rows.map((c) => (who.role === 'customer' ? customerView(c) : row(c))));
    }
    if (path === '/audit') {
      if (who.role !== 'manager') return fail(403, { code: 'FORBIDDEN', message: `Your role (${who.role}) cannot do this.` });
      const q = url.searchParams;
      let id = 0;
      const all = cases.flatMap((c) => c.audit.map((a) => ({ ...a, id: ++id, complaint_id: c.complaint_id }))).reverse();
      const entries = all.filter((e) => (!q.get('actor') || e.actor === q.get('actor'))
        && (!q.get('action') || e.action === q.get('action'))
        && (!q.get('case') || e.complaint_id.includes(q.get('case')!))
        && (q.get('people_only') !== 'true' || e.actor !== 'agent'));
      return json(200, { entries, actors: [...new Set(all.map((e) => e.actor).filter((a) => a !== 'agent'))].sort(),
        actions: [...new Set(all.map((e) => e.action))].sort() });
    }
    if (path === '/cases/counts') {
      if (who.role === 'customer') return fail(403, { code: 'FORBIDDEN', message: 'Your role (customer) cannot do this.' });
      const counts: Record<string, number> = {};
      cases.filter((c) => visible(who, c)).forEach((c) => (counts[c.status] = (counts[c.status] ?? 0) + 1));
      return json(200, counts);
    }
    const match = /^\/cases\/([^/]+)(?:\/(approve|reject|flag|messages|holding-reply))?$/.exec(path);
    if (match) {
      const c = cases.find((x) => x.complaint_id === decodeURIComponent(match[1]));
      if (!c) return fail(404, 'not processed yet (is the worker running?)');
      if (!visible(who, c)) return fail(403, { code: 'FORBIDDEN', message: 'This case is not in your queue.', route: c.route });
      const action = match[2];
      if (!action) return json(200, who.role === 'customer' ? customerView(c) : c);
      const failsCheck = () => String(body.reply_text ?? '').includes('TXN-9999999')
        && fail(422, { error: 'reply failed the self-check', problems: ['Reply mentions TXN-9999999, which is not in the evidence'] });
      if (action === 'approve') {
        const refused = failsCheck();
        if (refused) return refused;
        c.status = 'APPROVED';
        act(c, who.username, 'human_action', JSON.stringify({ action: body.reply_text ? 'edit_approve' : 'approve',
          actor: who.username, reason: body.note ?? '' }));
        act(c, who.username, 'approved', body.reply_text ? 'edited' : 'as drafted');
      }
      if (action === 'reject') {
        c.status = 'REJECTED';
        act(c, who.username, 'rejected', body.note ?? '');
        act(c, who.username, 'human_action', JSON.stringify({ action: 'reject', actor: who.username, reason: body.note ?? '' }));
      }
      if (action === 'holding-reply') {
        if (who.role !== 'fraud' && who.role !== 'manager') return fail(403, { code: 'FORBIDDEN', message: 'Your role cannot do this.' });
        if (c.status !== 'FRAUD_QUEUE') return fail(409, `${c.complaint_id} is not with the fraud team`);
        if (c.audit.some((a) => a.action === 'holding_reply_sent')) return fail(409, 'the holding reply has already been sent');
        const refused = failsCheck();
        if (refused) return refused;
        act(c, who.username, 'holding_reply_sent', body.reply_text ? 'edited' : 'as drafted');
        act(c, who.username, 'reply_sent', body.reply_text ?? c.reply_text);
      }
      if (action === 'flag') act(c, who.username, 'flagged_for_review', body.note);
      c.updated_at = `2026-10-22 12:${String(calls.length).padStart(2, '0')}:00`;
      return json(200, c);
    }
    return fail(404, 'Not Found');
  });

  vi.stubGlobal('fetch', fetchImpl);
  return { calls, cases, signUp: (id: string, password: string) => signedUp.set(id, password) };
}
