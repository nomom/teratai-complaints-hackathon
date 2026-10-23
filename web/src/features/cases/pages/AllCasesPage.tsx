import { FilterX } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Alert, Button, EmptyState, PageHeader, Select, Spinner, TextField } from '@/components/ui';
import { useUser } from '@/features/auth/AuthProvider';

import { CaseView } from '../components/CaseView';
import { QueueTable, type Column } from '../components/QueueTable';
import { useCaseList } from '../hooks';
import {
  activeCount,
  amount,
  CATEGORIES,
  matchesFilters,
  NO_FILTERS,
  optionsOf,
  OUTCOMES,
  PRIORITIES,
  type CaseFilters,
} from '../lib/filters';
import { FILTER_STATUSES, QUEUE_STATUSES, STATUS } from '../lib/status';
import type { CaseStatus } from '../types';
import styles from './pages.module.css';

const COLUMNS: Column[] = ['case', 'status', 'category', 'outcome', 'refund', 'priority', 'checked', 'updated'];
const FILTERS = [
  { value: 'all', label: 'All' },
  ...FILTER_STATUSES.map((s) => ({ value: s, label: STATUS[s].label })),
  { value: 'flagged', label: 'Flagged for review' },
];
const CATEGORY_OPTIONS = optionsOf(CATEGORIES, 'All categories');
const OUTCOME_OPTIONS = optionsOf(OUTCOMES, 'Any outcome');
const PRIORITY_OPTIONS = optionsOf(PRIORITIES, 'Any priority');

/** Every case the role may see, newest first; search by ID, narrow by status, category, outcome, priority and
 *  refund amount, and select one to open it. The status filter asks the API; the rest filter the loaded list. */
export function AllCasesPage() {
  const user = useUser();
  const [filter, setFilter] = useState('all');
  const [filters, setFilters] = useState<CaseFilters>(NO_FILTERS);
  const [selected, setSelected] = useState<string | null>(null);
  const statuses = filter === 'all' || filter === 'flagged' ? undefined : [filter as CaseStatus];
  const query = useCaseList(statuses);
  const loaded = useMemo(
    () => (filter === 'flagged' ? (query.data ?? []).filter((r) => r.flagged) : (query.data ?? [])),
    [query.data, filter],
  );
  const rows = useMemo(() => loaded.filter((r) => matchesFilters(r, filters)), [loaded, filters]);
  const narrowed = activeCount(filters);
  const title = filter === 'all' ? 'All cases' : (FILTERS.find((f) => f.value === filter)?.label ?? 'Cases');
  const open = rows.find((r) => r.complaint_id === selected);

  const min = amount(filters.refundMin);
  const max = amount(filters.refundMax);
  const rangeError = min !== null && max !== null && min > max ? 'Must be at least the "from" amount.' : undefined;
  const set = (key: keyof CaseFilters) => (value: string) => setFilters((f) => ({ ...f, [key]: value }));

  return (
    <>
      <PageHeader title={`${title} (${rows.length})`}
        subtitle={`Most recently updated first. Select a row to open the case.${user.role === 'manager' ? '' : ' Only cases in your queue.'}`} />

      <section className={styles.filterPanel} aria-label="Search and filters">
        <div className={styles.filters}>
          <div className={styles.searchCell}>
            <TextField label="Search" type="search" placeholder="Complaint ID, customer ID or transaction ID"
              value={filters.search} onChange={(e) => set('search')(e.target.value)} />
          </div>
          <div className={styles.statusCell}>
            <Select label="Status" value={filter} options={FILTERS} onValueChange={(v) => {
              setFilter(v);
              setSelected(null);
            }} />
          </div>
          <div className={styles.categoryCell}>
            <Select label="Category" value={filters.category} options={CATEGORY_OPTIONS} onValueChange={set('category')} />
          </div>
          <Select label="Outcome" value={filters.outcome} options={OUTCOME_OPTIONS} onValueChange={set('outcome')} />
          <Select label="Priority" value={filters.priority} options={PRIORITY_OPTIONS} onValueChange={set('priority')} />
          <TextField label="Refund from (RM)" type="number" inputMode="decimal" min={0} step="0.01" placeholder="0.00"
            value={filters.refundMin} onChange={(e) => set('refundMin')(e.target.value)} />
          <TextField label="Refund to (RM)" type="number" inputMode="decimal" min={0} step="0.01" placeholder="Any"
            value={filters.refundMax} onChange={(e) => set('refundMax')(e.target.value)} error={rangeError} />
        </div>
        <div className={styles.filterFooter}>
          <p className={styles.caption} aria-live="polite">
            {narrowed > 0
              ? `${rows.length} of ${loaded.length} cases match ${narrowed === 1 ? '1 filter' : `${narrowed} filters`}.`
              : `${loaded.length} cases.`}
          </p>
          {narrowed > 0 && (
            <Button variant="ghost" icon={FilterX} onClick={() => setFilters(NO_FILTERS)}>Clear filters</Button>
          )}
        </div>
      </section>

      {query.isPending && <Spinner label="Loading cases" />}
      {query.isError && <Alert tone="error">{query.error.message}</Alert>}
      {query.isSuccess && rows.length === 0 && (
        <EmptyState title="No cases match">
          {narrowed > 0 ? 'Try a shorter search, or clear the filters.' : 'Choose another status above.'}
        </EmptyState>
      )}
      {rows.length > 0 && (
        <QueueTable rows={rows} columns={COLUMNS} selectedId={selected} onSelect={setSelected} caption={title} />
      )}
      {open && <CaseView key={open.complaint_id} caseId={open.complaint_id} actions={QUEUE_STATUSES.includes(open.status)} />}
    </>
  );
}
