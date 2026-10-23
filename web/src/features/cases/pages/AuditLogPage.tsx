import { clsx } from 'clsx';
import { useState } from 'react';

import { Alert, EmptyState, PageHeader, Select, Spinner, Switch, TextField } from '@/components/ui';
import { nice } from '@/lib/format';

import { CaseView } from '../components/CaseView';
import tableStyles from '../components/QueueTable.module.css';
import { useAuditLog } from '../hooks';
import { readable } from '../lib/audit';
import styles from './pages.module.css';

const ANY = 'any';

/** Every action on every case, newest first (manager only): who did what, when. Filter by person, action or case;
 *  select a row to open that case below. */
export function AuditLogPage() {
  const [actor, setActor] = useState(ANY);
  const [action, setAction] = useState(ANY);
  const [caseId, setCaseId] = useState('');
  const [peopleOnly, setPeopleOnly] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  const query = useAuditLog({ actor: actor === ANY ? undefined : actor, action: action === ANY ? undefined : action,
    case: caseId, peopleOnly });
  const entries = query.data?.entries ?? [];

  return (
    <>
      <PageHeader title="Audit log" subtitle="Who did what, when, on every case. Newest first; the last 500 entries." />

      <section className={styles.filterPanel} aria-label="Audit filters">
        <div className={styles.filters}>
          <Select label="Who" value={actor} onValueChange={setActor}
            options={[{ value: ANY, label: 'Anyone' }, ...(query.data?.actors ?? []).map((a) => ({ value: a, label: a }))]} />
          <Select label="Action" value={action} onValueChange={setAction}
            options={[{ value: ANY, label: 'Any action' },
              ...(query.data?.actions ?? []).map((a) => ({ value: a, label: nice(a) }))]} />
          <TextField label="Case" type="search" placeholder="Complaint ID" value={caseId}
            onChange={(e) => setCaseId(e.target.value)} />
        </div>
        <div className={styles.filterFooter}>
          <Switch label="People only (hide the agent's own entries)" checked={peopleOnly} onCheckedChange={setPeopleOnly} />
          <p className={styles.caption}>{`${entries.length} entr${entries.length === 1 ? 'y' : 'ies'}`}</p>
        </div>
      </section>

      {query.isPending && <Spinner label="Loading the audit log" />}
      {query.isError && <Alert tone="error">{query.error.message}</Alert>}
      {query.isSuccess && entries.length === 0 && (
        <EmptyState title="No entries match">Choose another person or action above.</EmptyState>
      )}
      {entries.length > 0 && (
        <div className={tableStyles.frame}>
          <table className={tableStyles.table} aria-label="Audit log, newest first">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Case</th>
                <th scope="col">Who</th>
                <th scope="col">Action</th>
                <th scope="col">Detail</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const selected = e.complaint_id === open;
                return (
                  <tr key={e.id} className={clsx(tableStyles.row, selected && tableStyles.selected)}
                    aria-selected={selected} tabIndex={0} onClick={() => setOpen(e.complaint_id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        setOpen(e.complaint_id);
                      }
                    }}>
                    <td>{e.ts}</td>
                    <td className={tableStyles.id}>{e.complaint_id}</td>
                    <td>{e.actor}</td>
                    <td>{nice(e.action)}</td>
                    <td className={styles.auditDetail} title={e.detail}>{readable(e.detail)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {open && <CaseView key={open} caseId={open} />}
    </>
  );
}
