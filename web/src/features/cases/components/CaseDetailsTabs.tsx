import { Alert, Tabs } from '@/components/ui';
import { money } from '@/lib/format';

import type { CaseDetail } from '../types';
import styles from './CaseView.module.css';

function Json({ value }: { value: unknown }) {
  return <pre className={styles.json}>{JSON.stringify(value, null, 2)}</pre>;
}

/** The full record behind the summary, one tab each. Content matches the officer view in agent/summary.py's spirit. */
export function CaseDetailsTabs({ caseItem }: { caseItem: CaseDetail }) {
  const { record, audit } = caseItem;
  const { complaint, extraction, decision } = record;
  const evidence = decision.evidence ?? {};
  const reply = evidence.reply ?? {};
  const usage = record.llm_usage ?? {};

  const facts: [string, unknown][] = [
    ['Customer', evidence.customer],
    ['Priority', evidence.priority],
    ['Reply language', reply.language ? { language: reply.language, why: reply.language_why } : null],
    ['Account', evidence.account],
    ['Matched transaction', evidence.txn],
    ['Identical earlier charge', evidence.twin],
    ['Reversal', evidence.reversal],
    ['ATM journal', evidence.atm_journal],
    ['Fee schedule row', evidence.fee_schedule],
    ['Fee that should have been charged', evidence.fee_due == null ? null : money(evidence.fee_due)],
    ['How the date was read', evidence.date_resolution],
    ['Candidates considered (score, id)', evidence.candidates],
    ['Policy settings in force', evidence.policy],
  ];
  const readFromMessage = Object.fromEntries(
    Object.entries(extraction).filter(([, v]) => v !== '' && v !== null && v !== false
      && !(Array.isArray(v) && v.length === 0) && !(typeof v === 'object' && v && Object.keys(v).length === 0)),
  );

  return (
    <Tabs label="Case details" items={[
      {
        value: 'message',
        label: "Customer's message",
        content: (
          <div>
            <p className={styles.meta}>
              {complaint.channel} · received {complaint.received_at}
              {complaint.subject ? ` · subject: ${complaint.subject}` : ''}
            </p>
            <p className={styles.quote}>{complaint.text}</p>
          </div>
        ),
      },
      {
        value: 'evidence',
        label: 'Full evidence',
        content: (
          <dl className={styles.facts}>
            {facts.filter(([, value]) => value).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{typeof value === 'object' ? <Json value={value} /> : String(value)}</dd>
              </div>
            ))}
          </dl>
        ),
      },
      {
        value: 'agent',
        label: 'How the agent decided',
        content: (
          <div className={styles.stack}>
            <section>
              <h4 className={styles.h4}>Decision reasons (internal)</h4>
              <ul className={styles.list}>
                {(decision.reasons ?? []).map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            </section>
            <section>
              <h4 className={styles.h4}>What it read from the message (by {extraction.source ?? 'rules'})</h4>
              <Json value={readFromMessage} />
            </section>
            {reply.source && (
              <section>
                <h4 className={styles.h4}>Reply written by: {reply.source}</h4>
                {(reply.rejected_drafts ?? []).map((draft, i) => (
                  <div key={i}>
                    <Alert tone="warning">{`Draft ${i + 1} (${draft.source}) was rejected: ${draft.problems.join('; ')}`}</Alert>
                    <p className={styles.quote}>{draft.text}</p>
                  </div>
                ))}
              </section>
            )}
            <section>
              <h4 className={styles.h4}>Steps</h4>
              <table className={styles.mini}>
                <thead><tr><th scope="col">Step</th><th scope="col">ms</th></tr></thead>
                <tbody>
                  {(record.trace ?? []).map((t, i) => <tr key={i}><td>{t.step}</td><td>{t.ms}</td></tr>)}
                </tbody>
              </table>
              <p className={styles.meta}>
                LLM: {usage.calls ?? 0} calls, {usage.input_tokens ?? 0} input / {usage.output_tokens ?? 0} output tokens
                {usage.failures?.length ? `, failures: ${usage.failures.join(', ')}` : ''}
              </p>
            </section>
          </div>
        ),
      },
      {
        value: 'audit',
        label: 'Audit log',
        content: (
          <div className={styles.scroll}>
            <table className={styles.mini}>
              <thead><tr><th scope="col">Time</th><th scope="col">Actor</th><th scope="col">Action</th><th scope="col">Detail</th></tr></thead>
              <tbody>
                {audit.map((a, i) => (
                  <tr key={i}><td>{a.ts}</td><td>{a.actor}</td><td>{a.action}</td><td className={styles.detail}>{a.detail}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ),
      },
    ]} />
  );
}
