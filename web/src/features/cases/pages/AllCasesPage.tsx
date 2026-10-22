import { useMemo, useState } from 'react';

import { Alert, EmptyState, PageHeader, Select, Spinner } from '@/components/ui';
import { useUser } from '@/features/auth/AuthProvider';

import { CaseView } from '../components/CaseView';
import { QueueTable, type Column } from '../components/QueueTable';
import { useCaseList } from '../hooks';
import { FILTER_STATUSES, QUEUE_STATUSES, STATUS } from '../lib/status';
import type { CaseStatus } from '../types';
import styles from './pages.module.css';

const COLUMNS: Column[] = ['case', 'status', 'category', 'outcome', 'refund', 'priority', 'checked', 'updated'];
const FILTERS = [
  { value: 'all', label: 'All' },
  ...FILTER_STATUSES.map((s) => ({ value: s, label: STATUS[s].label })),
  { value: 'flagged', label: 'Flagged for review' },
];

/** Every case the role may see, newest first; filter by status or by flag, select one to open it. */
export function AllCasesPage() {
  const user = useUser();
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState<string | null>(null);
  const statuses = filter === 'all' || filter === 'flagged' ? undefined : [filter as CaseStatus];
  const query = useCaseList(statuses);
  const rows = useMemo(
    () => (filter === 'flagged' ? (query.data ?? []).filter((r) => r.flagged) : (query.data ?? [])),
    [query.data, filter],
  );
  const title = filter === 'all' ? 'All cases' : (FILTERS.find((f) => f.value === filter)?.label ?? 'Cases');
  const open = rows.find((r) => r.complaint_id === selected);

  return (
    <>
      <PageHeader title={`${title} (${rows.length})`}
        subtitle={`Most recently updated first. Select a row to open the case.${user.role === 'manager' ? '' : ' Only cases in your queue.'}`} />
      <div className={styles.filter}>
        <Select label="Show" value={filter} options={FILTERS} onValueChange={(v) => {
          setFilter(v);
          setSelected(null);
        }} />
      </div>
      {query.isPending && <Spinner label="Loading cases" />}
      {query.isError && <Alert tone="error">{query.error.message}</Alert>}
      {query.isSuccess && rows.length === 0 && <EmptyState title="No cases here">Choose another filter above.</EmptyState>}
      {rows.length > 0 && (
        <QueueTable rows={rows} columns={COLUMNS} selectedId={selected} onSelect={setSelected} caption={title} />
      )}
      {open && <CaseView key={open.complaint_id} caseId={open.complaint_id} actions={QUEUE_STATUSES.includes(open.status)} />}
    </>
  );
}
