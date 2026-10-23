import { Check, Pencil, Send, ShieldCheck, X } from 'lucide-react';
import { useState } from 'react';

import { useFlash } from '@/app/providers/FlashProvider';
import { Alert, Badge, Button, TextArea } from '@/components/ui';
import { ApiError } from '@/lib/apiClient';
import { money } from '@/lib/format';

import { useApprove, useHoldingReply, useReject } from '../hooks';
import type { CaseDetail } from '../types';
import styles from './CaseView.module.css';

const LANGUAGE: Record<string, string> = { EN: 'English', MS: 'Malay' };

/** The self-check result for the reply on screen. Once the reply is edited the agent's result no longer applies, so
 *  it says the check runs again on the exact text when it is sent, instead of a green "verified" for the old draft. */
export function SelfCheckLine({ warnings, edited = false }: { warnings: string[]; edited?: boolean }) {
  if (edited) {
    return (
      <p className={styles.checked}>
        <Badge tone="neutral" icon={Pencil}>Edited</Badge>
        <span>The self-check runs again on your text when you send it</span>
      </p>
    );
  }
  if (warnings.length > 0) return <Alert tone="error" items={warnings}>The reply check found problems</Alert>;
  return (
    <p className={styles.checked}>
      <Badge tone="success" icon={ShieldCheck}>Self-check verified</Badge>
      <span>Every transaction, amount and date in the reply belongs to this case's evidence</span>
    </p>
  );
}

type Step = 'edit' | 'review' | 'reject';

/** The reply and what a person can do with it. Approval queue: review, then send (the money and the reply in one
 *  confirmation), or reject with a reason. Fraud queue: send the holding reply; the case stays with the fraud team.
 *  The self-check runs again on the exact text going out, edited or not. */
export function ReplyActions({ caseItem }: { caseItem: CaseDetail }) {
  const id = caseItem.complaint_id;
  const fraud = caseItem.status === 'FRAUD_QUEUE';
  const held = caseItem.audit.findLast((a) => a.action === 'holding_reply_sent');
  const { flash } = useFlash();
  const approve = useApprove();
  const reject = useReject();
  const hold = useHoldingReply();
  const [text, setText] = useState(caseItem.reply_text);
  const [step, setStep] = useState<Step>('edit');
  const [reason, setReason] = useState('');
  const [problem, setProblem] = useState<{ message: string; items?: string[] } | null>(null);

  const edited = text !== caseItem.reply_text;
  const refund = caseItem.outcome === 'REFUND' && (caseItem.refund_amount_myr ?? 0) > 0 ? caseItem.refund_amount_myr : null;
  const busy = approve.isPending || reject.isPending || hold.isPending;

  function go(next: Step) {
    setStep(next);
    setReason('');
    setProblem(null);
  }

  function failed(e: unknown) {
    if (e instanceof ApiError && e.status === 422) {
      setProblem({ message: 'Not sent: the reply failed the self-check.', items: e.field<string[]>('problems') });
    } else {
      setProblem({ message: e instanceof Error ? e.message : 'Something went wrong.' });
    }
  }

  // mutateAsync, not mutate(..., { onSuccess }): the case leaves the queue and this panel unmounts before a per-call
  // onSuccess would run, and React Query skips those for unmounted components. The flash lives above, so it shows.
  async function onSend() {
    setProblem(null);
    try {
      await approve.mutateAsync({ id, replyText: edited ? text : null, note: reason.trim() });
      flash('success', refund ? `${id} approved: the ${money(refund)} refund and the reply were sent.`
        : `${id} approved and the reply was sent.`);
    } catch (e) {
      setStep('edit');
      failed(e);
    }
  }

  async function onReject() {
    setProblem(null);
    try {
      await reject.mutateAsync({ id, note: reason.trim() });
      flash('success', `${id} rejected. No reply was sent; it is in Rejected for you to handle.`);
    } catch (e) {
      failed(e);
    }
  }

  async function onHold() {
    setProblem(null);
    try {
      await hold.mutateAsync({ id, replyText: edited ? text : null });
      flash('success', `${id}: holding reply sent. The case stays with the fraud team.`);
    } catch (e) {
      failed(e);
    }
  }

  if (fraud && held) {
    return (
      <div className={styles.block}>
        <Alert tone="success">
          {`Holding reply sent by ${held.actor} (${held.ts}). The case stays with the fraud team for the investigation.`}
        </Alert>
        <TextArea label="Holding reply sent to the customer" rows={6} value={caseItem.reply_text} readOnly />
      </div>
    );
  }

  return (
    <div className={styles.block}>
      <SelfCheckLine warnings={caseItem.summary.warnings} edited={edited} />
      <TextArea label={fraud ? 'Holding reply to the customer (edit before sending if needed)'
        : 'Reply to the customer (edit before approving if needed)'} rows={9} value={text}
        readOnly={step !== 'edit'} onChange={(e) => {
          setText(e.target.value);
          setProblem(null);
        }} />
      {problem && (
        <Alert tone="error" items={problem.items}>
          {problem.message}
        </Alert>
      )}

      {step === 'edit' && (
        <div className={styles.actions}>
          {fraud ? (
            <Button variant="primary" icon={Send} onClick={onHold} loading={hold.isPending} disabled={busy}>
              Send holding reply
            </Button>
          ) : (
            <Button variant="primary" icon={Check} onClick={() => go('review')} disabled={busy}>
              Review and send
            </Button>
          )}
          <Button variant="danger" icon={X} onClick={() => go('reject')} disabled={busy}>
            Reject
          </Button>
        </div>
      )}

      {step === 'review' && (
        <section className={styles.panel} aria-labelledby={`review-${id}`}>
          <h3 id={`review-${id}`} className={styles.panelTitle}>Check before you send</h3>
          <dl className={styles.facts}>
            <div><dt>Case</dt><dd>{id}</dd></div>
            <div><dt>Customer</dt><dd>{caseItem.customer_id}</dd></div>
            <div><dt>Decision</dt><dd>{caseItem.summary.decision}</dd></div>
            <div><dt>Reply language</dt><dd>{LANGUAGE[caseItem.reply_language ?? ''] ?? caseItem.reply_language}</dd></div>
          </dl>
          {edited && (
            <TextArea label="Why did you change the reply? (required)" rows={2} value={reason}
              onChange={(e) => setReason(e.target.value)} />
          )}
          <p className={styles.panelNote}>
            {refund ? `The ${money(refund)} refund is recorded and the reply goes to the customer as soon as you confirm.`
              : 'The reply goes to the customer as soon as you confirm.'}
          </p>
          <div className={styles.actions}>
            <Button variant="primary" icon={Send} onClick={onSend} loading={approve.isPending}
              disabled={busy || (edited && !reason.trim())}>
              {refund ? `Send ${money(refund)} refund` : 'Send reply'}
            </Button>
            <Button onClick={() => go('edit')} disabled={busy}>Back</Button>
          </div>
        </section>
      )}

      {step === 'reject' && (
        <section className={styles.panel} aria-labelledby={`reject-${id}`}>
          <h3 id={`reject-${id}`} className={styles.panelTitle}>Reject this case</h3>
          <p className={styles.panelNote}>
            Nothing is sent to the customer. The case moves to Rejected, where you handle it yourself.
          </p>
          <TextArea label="Reason for rejecting (required)" rows={3} value={reason}
            onChange={(e) => setReason(e.target.value)} />
          <div className={styles.actions}>
            <Button variant="danger" icon={X} onClick={onReject} loading={reject.isPending}
              disabled={busy || !reason.trim()}>
              Reject case
            </Button>
            <Button onClick={() => go('edit')} disabled={busy}>Back</Button>
          </div>
        </section>
      )}
    </div>
  );
}
