import { useMemo, useState } from 'react';

import { Alert, EmptyState, PageHeader, Spinner, Switch } from '@/components/ui';

import { CaseView } from '../components/CaseView';
import { QueueTable, type Column } from '../components/QueueTable';
import { useCaseList } from '../hooks';
import type { QueueConfig } from '../lib/queues';
import { sortByUrgency } from '../lib/sort';
import styles from './pages.module.css';

const COLUMNS: Column[] = ['priority', 'case', 'refund', 'sla', 'category', 'outcome', 'status', 'checked'];

/** A queue: every case in it, most urgent first, with the selected case (the first by default) opened below. */
export function QueuePage({ config }: { config: QueueConfig }) {
  const query = useCaseList(config.statuses);
  const [selected, setSelected] = useState<string | null>(null);
  const [onlyFlagged, setOnlyFlagged] = useState(false);

  const all = query.data;
  const rows = useMemo(() => {
    const sorted = sortByUrgency(all ?? []);
    return onlyFlagged ? sorted.filter((r) => r.flagged) : sorted;
  }, [all, onlyFlagged]);
  const flaggedCount = useMemo(() => (all ?? []).filter((r) => r.flagged).length, [all]);
  const openId = rows.some((r) => r.complaint_id === selected) ? selected : (rows[0]?.complaint_id ?? null);

  return (
    <>
      <PageHeader title={`${config.title} (${all?.length ?? 0})`} subtitle={config.subtitle} />
      {query.isPending && <Spinner label="Loading the queue" />}
      {query.isError && <Alert tone="error">{query.error.message}</Alert>}
      {config.flagFilter && flaggedCount > 0 && (
        <div className={styles.toolbar}>
          <Switch label={`Only flagged for review (${flaggedCount})`} checked={onlyFlagged} onCheckedChange={setOnlyFlagged} />
        </div>
      )}
      {query.isSuccess && rows.length === 0 && (
        <EmptyState title={`Nothing in ${config.title.toLowerCase()}`}>{config.empty}</EmptyState>
      )}
      {rows.length > 0 && (
        <>
          <p className={styles.caption}>Sorted by priority, then time left to acknowledge. Select a row to open the case.</p>
          <QueueTable rows={rows} columns={COLUMNS} selectedId={openId} onSelect={setSelected}
            caption={`${config.title}, most urgent first`} />
          {openId && <CaseView key={openId} caseId={openId} actions={config.actions} />}
        </>
      )}
    </>
  );
}
