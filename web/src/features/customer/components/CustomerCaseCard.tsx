import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

import { Alert, Spinner } from '@/components/ui';
import { CustomerStatusBadge } from '@/features/cases/components/Badges';
import { CustomerReplyBox } from '@/features/cases/components/CustomerReplyBox';
import { useOwnCase } from '@/features/cases/hooks';
import type { CustomerCase } from '@/features/cases/types';

import { Thread } from './Thread';
import styles from './customer.module.css';

/** One of the customer's cases; opening it loads the conversation. A case waiting for their answer starts open. */
export function CustomerCaseCard({ row }: { row: CustomerCase }) {
  const [open, setOpen] = useState(row.status === 'AWAITING_CUSTOMER');
  return (
    <details className={styles.card} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className={styles.summary}>
        <ChevronDown className={styles.chevron} aria-hidden />
        <span className={styles.caseId}>{row.complaint_id}</span>
        <CustomerStatusBadge status={row.status} />
        <span className={styles.preview}>{row.text}</span>
      </summary>
      {open && <CaseConversation id={row.complaint_id} />}
    </details>
  );
}

function CaseConversation({ id }: { id: string }) {
  const query = useOwnCase(id);
  if (query.isPending) return <Spinner label="Loading the conversation" />;
  if (query.isError) return <Alert tone="error">{query.error.message}</Alert>;
  const caseItem = query.data;
  return (
    <div className={styles.body}>
      <p className={styles.meta}>
        {caseItem.channel} · sent {caseItem.received_at}
      </p>
      <Thread caseItem={caseItem} />
      {(caseItem.status === 'PENDING_APPROVAL' || caseItem.status === 'FRAUD_QUEUE') && (
        <Alert tone="info">Our team is reviewing your case. We'll reply here.</Alert>
      )}
      {caseItem.status === 'AWAITING_CUSTOMER' && (
        <CustomerReplyBox caseId={id} updatedAt={caseItem.updated_at} label="Your answer"
          doneText="Thanks, your answer was sent. We'll take it from here." />
      )}
    </div>
  );
}
