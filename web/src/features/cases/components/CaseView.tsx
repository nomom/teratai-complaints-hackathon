import { Alert, Badge, Card, Spinner, TextArea, Tile, TileGrid } from '@/components/ui';
import { useUser } from '@/features/auth/AuthProvider';
import { money, nice } from '@/lib/format';

import { useCase } from '../hooks';
import { slaLeft } from '../lib/sla';
import { QUEUE_STATUSES, SENT_STATUSES } from '../lib/status';
import type { CaseDetail } from '../types';
import { PriorityBadge, SlaBadge, StatusBadge } from './Badges';
import { CaseDetailsTabs } from './CaseDetailsTabs';
import { CustomerReplyBox } from './CustomerReplyBox';
import { FlagForReview } from './FlagForReview';
import { ReplyActions, SelfCheckLine } from './ReplyActions';
import styles from './CaseView.module.css';

const ROUTE_LABEL: Record<string, string> = {
  AUTO_RESOLVE: 'Auto-resolve',
  HUMAN_APPROVAL: 'Human approval',
  FRAUD_TEAM: 'Fraud team',
};

/** Loads and shows one case; `actions` offers approve/reject when the case waits in a queue. */
export function CaseView({ caseId, actions = false }: { caseId: string; actions?: boolean }) {
  const query = useCase(caseId);
  if (query.isPending) return <Spinner label={`Loading ${caseId}`} />;
  if (query.isError) return <Alert tone="error">{query.error.message}</Alert>;
  return <CaseBody caseItem={query.data} actions={actions} />;
}

/** The summary an officer needs to act comes first; the reply and actions next; the details one tab away. */
export function CaseBody({ caseItem, actions }: { caseItem: CaseDetail; actions: boolean }) {
  const user = useUser();
  const { summary } = caseItem;
  const canAct = actions && user.role !== 'customer' && QUEUE_STATUSES.includes(caseItem.status);
  const sent = SENT_STATUSES.includes(caseItem.status);
  const flags = caseItem.audit.filter((a) => a.action === 'flagged_for_review');
  const rejected = caseItem.status === 'REJECTED' ? caseItem.audit.findLast((a) => a.action === 'rejected') : undefined;

  return (
    <article className={styles.case} aria-label={`Case ${caseItem.complaint_id}`}>
      <div className={styles.header}>
        <h2 className={styles.id}>{caseItem.complaint_id}</h2>
        <StatusBadge status={caseItem.status} />
        <PriorityBadge priority={caseItem.priority} />
        <SlaBadge left={slaLeft(caseItem)} />
        <Badge tone="neutral">Reply {caseItem.reply_language ?? '-'}</Badge>
      </div>
      <p className={styles.meta}>
        {caseItem.channel} · received {caseItem.received_at} · customer {caseItem.customer_id}
      </p>

      <p className={styles.headline}>{summary.headline}</p>
      {summary.why_here.length > 1 ? (
        <Alert tone={summary.tone} items={summary.why_here}>Why this case is here</Alert>
      ) : (
        <Alert tone={summary.tone}>{summary.why_here[0]}</Alert>
      )}

      <Card title="What happened">
        <p>{summary.story}</p>
        <p className={styles.decision}>
          <strong>Decision:</strong> {summary.decision}
        </p>
      </Card>

      <div className={styles.block}>
        <TileGrid>
          <Tile label="Category">{nice(caseItem.category)}</Tile>
          <Tile label="Matched transaction">{caseItem.matched_txn_id ?? '-'}</Tile>
          <Tile label="Outcome">{nice(caseItem.outcome)}</Tile>
          <Tile label="Refund">{money(caseItem.refund_amount_myr)}</Tile>
          <Tile label="Route">{ROUTE_LABEL[caseItem.route ?? ''] ?? '-'}</Tile>
        </TileGrid>
      </div>

      {flags.map((f) => (
        <Alert key={f.ts + f.actor} tone="warning">{`Flagged for review by ${f.actor} (${f.ts}): ${f.detail}`}</Alert>
      ))}
      {summary.key_row && <pre className={styles.keyRow}>{summary.key_row}</pre>}
      {rejected && (
        <Alert tone="warning">
          {`Rejected by ${rejected.actor} (${rejected.ts}): ${rejected.detail || 'no reason given'}. Nothing from the `
            + 'agent went out: contact the customer and handle the case yourself.'}
        </Alert>
      )}
      {/* With actions, ReplyActions shows the check for the text being edited; otherwise it's the agent's reply */}
      {!canAct && <SelfCheckLine warnings={summary.warnings} />}

      {canAct ? (
        <ReplyActions key={caseItem.complaint_id + caseItem.updated_at} caseItem={caseItem} />
      ) : (
        <div className={styles.block}>
          <TextArea label={sent ? 'Reply sent to the customer' : 'Reply to the customer'} rows={8}
            value={caseItem.reply_text} readOnly />
          {sent && <FlagForReview caseId={caseItem.complaint_id} />}
        </div>
      )}
      {caseItem.status === 'AWAITING_CUSTOMER' && (
        <div className={styles.block}>
          <CustomerReplyBox caseId={caseItem.complaint_id} updatedAt={caseItem.updated_at}
            label="Customer's answer to the follow-up question"
            doneText={`The customer's answer on ${caseItem.complaint_id} was sent to the agent.`} />
        </div>
      )}
      <CaseDetailsTabs caseItem={caseItem} />
    </article>
  );
}
