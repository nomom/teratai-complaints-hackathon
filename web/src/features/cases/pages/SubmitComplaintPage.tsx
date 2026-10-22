import { useState, type FormEvent } from 'react';

import { Alert, Button, Card, PageHeader, Select, Spinner, TextArea, TextField } from '@/components/ui';
import { ApiError } from '@/lib/apiClient';

import * as casesApi from '../api';
import { CaseBody } from '../components/CaseView';
import { waitForWorker } from '../lib/waitForWorker';
import type { CaseDetail } from '../types';
import styles from './pages.module.css';

// Transactions run April-September 2026, so live complaints default to a received time just after that.
const DEFAULT_RECEIVED = '2026-09-30 18:00';
const CHANNELS = ['App chat', 'Email', 'Call centre note', 'Branch form', 'Social media DM'].map((c) => ({ value: c, label: c }));

type Outcome =
  | { kind: 'waiting'; id: string }
  | { kind: 'shown'; caseItem: CaseDetail }
  | { kind: 'routed'; id: string; route: string }
  | { kind: 'late'; id: string }
  | { kind: 'error'; message: string };

/** Intake for any customer, e.g. a call-centre note or a live-round row. Shows the case if it lands in your queue. */
export function SubmitComplaintPage() {
  const [form, setForm] = useState({ complaint_id: '', customer_id: 'CUS-00150', channel: 'App chat',
    received_at: DEFAULT_RECEIVED, subject: '', text: '' });
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const set = (field: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [field]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.text.trim()) return;
    let id = '';
    try {
      ({ complaint_id: id } = await casesApi.submitComplaint({
        ...form,
        complaint_id: form.complaint_id.trim() || undefined,
        customer_id: form.customer_id.trim(),
        received_at: form.received_at.trim(),
        subject: form.subject.trim(),
      }));
      setOutcome({ kind: 'waiting', id });
      const caseItem = await waitForWorker(() => casesApi.getCase(id));
      setOutcome(caseItem ? { kind: 'shown', caseItem } : { kind: 'late', id });
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {      // processed, but it went to another team's queue
        setOutcome({ kind: 'routed', id, route: e.field<string>('route') ?? 'another team' });
      } else {
        setOutcome({ kind: 'error', message: e instanceof Error ? e.message : 'Something went wrong.' });
      }
    }
  }

  return (
    <>
      <PageHeader title="New complaint" subtitle="Intake for any customer, e.g. a call-centre note or a live-round row." />
      <Card className={styles.formCard}>
        <form onSubmit={submit}>
          <TextField label="Complaint ID (optional, e.g. LIVE-01; generated if empty)" value={form.complaint_id}
            onChange={(e) => set('complaint_id')(e.target.value)} />
          <div className={styles.twoCols}>
            <TextField label="Customer ID" value={form.customer_id} onChange={(e) => set('customer_id')(e.target.value)} />
            <Select label="Channel" value={form.channel} options={CHANNELS} onValueChange={set('channel')} />
          </div>
          <div className={styles.twoCols}>
            <TextField label="Received at (YYYY-MM-DD HH:MM)" value={form.received_at}
              onChange={(e) => set('received_at')(e.target.value)} />
            <TextField label="Subject (optional)" value={form.subject} onChange={(e) => set('subject')(e.target.value)} />
          </div>
          <TextArea label="Complaint text" rows={6} value={form.text} onChange={(e) => set('text')(e.target.value)} />
          <Button type="submit" variant="primary" loading={outcome?.kind === 'waiting'} disabled={!form.text.trim()}>
            Submit
          </Button>
        </form>
      </Card>
      <SubmitOutcome outcome={outcome} />
    </>
  );
}

function SubmitOutcome({ outcome }: { outcome: Outcome | null }) {
  if (!outcome) return null;
  switch (outcome.kind) {
    case 'waiting':
      return <Spinner label={`${outcome.id} dropped into the inbox. Waiting for the worker...`} />;
    case 'shown':
      return <CaseBody caseItem={outcome.caseItem} actions={false} />;
    case 'routed':
      return <Alert tone="success">{`${outcome.id} was processed and routed to ${outcome.route}: not your queue.`}</Alert>;
    case 'late':
      return <Alert tone="warning">{`${outcome.id} is not processed yet. Is the worker (python -m app.worker) running?`}</Alert>;
    case 'error':
      return <Alert tone="error">{outcome.message}</Alert>;
  }
}
