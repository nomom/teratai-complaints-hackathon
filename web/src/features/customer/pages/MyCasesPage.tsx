import { Alert, EmptyState, PageHeader, Spinner } from '@/components/ui';
import { useOwnCases } from '@/features/cases/hooks';

import { CustomerCaseCard } from '../components/CustomerCaseCard';
import styles from '../components/customer.module.css';

export function MyCasesPage() {
  const query = useOwnCases();
  const rows = query.data ?? [];
  return (
    <>
      <PageHeader title={`My cases (${rows.length})`} subtitle="Your complaints and our replies." />
      {query.isPending && <Spinner label="Loading your cases" />}
      {query.isError && <Alert tone="error">{query.error.message}</Alert>}
      {query.isSuccess && rows.length === 0 && (
        <EmptyState title="You have no complaints with us">Use New complaint to tell us what went wrong.</EmptyState>
      )}
      <div className={styles.list}>
        {rows.map((row) => (
          <CustomerCaseCard key={row.complaint_id} row={row} />
        ))}
      </div>
    </>
  );
}
