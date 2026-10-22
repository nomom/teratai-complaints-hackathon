import { Check, X } from 'lucide-react';
import { useState } from 'react';

import { useFlash } from '@/app/providers/FlashProvider';
import { Alert, Button, TextArea } from '@/components/ui';
import { ApiError } from '@/lib/apiClient';

import { useApprove, useReject } from '../hooks';
import type { CaseDetail } from '../types';
import styles from './CaseView.module.css';

/** Edit the reply, then approve (the self-check runs again on the exact text going out) or reject. */
export function ReplyActions({ caseItem }: { caseItem: CaseDetail }) {
  const id = caseItem.complaint_id;
  const { flash } = useFlash();
  const approve = useApprove();
  const reject = useReject();
  const [text, setText] = useState(caseItem.reply_text);
  const [problem, setProblem] = useState<{ message: string; items?: string[] } | null>(null);

  function failed(e: unknown) {
    if (e instanceof ApiError && e.status === 422) {
      setProblem({ message: 'Not sent: the reply failed the self-check.', items: e.field<string[]>('problems') });
    } else {
      setProblem({ message: e instanceof Error ? e.message : 'Something went wrong.' });
    }
  }

  // mutateAsync, not mutate(..., { onSuccess }): the case leaves the queue and this panel unmounts before a per-call
  // onSuccess would run, and React Query skips those for unmounted components. The flash lives above, so it shows.
  async function onApprove() {
    setProblem(null);
    try {
      await approve.mutateAsync({ id, replyText: text === caseItem.reply_text ? null : text });
      flash('success', `${id} approved and the reply was sent.`);
    } catch (e) {
      failed(e);
    }
  }

  async function onReject() {
    setProblem(null);
    try {
      await reject.mutateAsync(id);
      flash('success', `${id} rejected. No reply was sent.`);
    } catch (e) {
      failed(e);
    }
  }

  const busy = approve.isPending || reject.isPending;
  return (
    <div className={styles.block}>
      <TextArea label="Reply to the customer (edit before approving if needed)" rows={9} value={text}
        onChange={(e) => setText(e.target.value)} />
      {problem && (
        <Alert tone="error" items={problem.items}>
          {problem.message}
        </Alert>
      )}
      <div className={styles.actions}>
        <Button variant="primary" icon={Check} onClick={onApprove} loading={approve.isPending} disabled={busy}>
          Approve and send
        </Button>
        <Button variant="danger" icon={X} onClick={onReject} loading={reject.isPending} disabled={busy}>
          Reject
        </Button>
      </div>
    </div>
  );
}
