import { FilterX } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Alert, Button, Card, EmptyState, PageHeader, Select, Spinner, TextField } from '@/components/ui';
import { useUser } from '@/features/auth/AuthProvider';
import { day, money } from '@/lib/format';

import { Donut } from '../components/Donut';
import { Gauge } from '../components/Gauge';
import { OutcomeByCategory } from '../components/OutcomeByCategory';
import { PeopleCard } from '../components/PeopleCard';
import { RankedTable } from '../components/RankedTable';
import { Scorecard } from '../components/Scorecard';
import { VolumeChart } from '../components/VolumeChart';
import { useDashboard } from '../hooks';
import {
  activeCount,
  ANY,
  DEFAULT_FILTERS,
  DIMENSIONS,
  PERIODS,
  rangeError,
  toParams,
  type DashboardFilters,
} from '../lib/filters';
import { delta, fillDays, LANGUAGE_COLOR, PRIORITY_COLOR, share, TARGETS } from '../lib/kpi';
import { autoBucket, DIMENSION_LABEL, shortDay, toColumns, valueLabel, type Bucket } from '../lib/series';
import type { Dashboard, DailyKpis, Dimension } from '../types';
import styles from './DashboardPage.module.css';

const BUCKETS: { value: Bucket; label: string }[] = [
  { value: 'day', label: 'Per day' },
  { value: 'week', label: 'Per week' },
];

const ANY_LABEL: Record<Dimension, string> = {
  status: 'Any status', route: 'Any route', category: 'All categories', outcome: 'Any outcome',
  priority: 'Any priority', channel: 'Any channel', language: 'Any language',
};

const count = (n: number) => n.toLocaleString('en-MY');

/** "Received 1 Sep 2026 to 30 Sep 2026." */
function periodText(applied: Dashboard['applied'], range: Dashboard['date_range']): string {
  const from = applied.date_from ?? range.first;
  const to = applied.date_to ?? range.last;
  if (!from || !to) return 'No complaints received yet.';
  return `Received ${day(from)} to ${day(to)}.`;
}

/** What the scorecards compare with: "the previous 30 days" or "1 Aug to 30 Aug". */
function comparedWith(filters: DashboardFilters, previous: Dashboard['previous']): string {
  if (!previous) return '';
  if (filters.period !== 'custom' && filters.period !== 'all') return `the previous ${filters.period} days`;
  return `${shortDay(previous.date_from)} to ${shortDay(previous.date_to)}`;
}

/**
 * KPI scorecards of the cases the signed-in role may see: an officer their approval queue's route, a fraud analyst
 * the fraud team's, a manager everything (and who acted on what). The API applies the role, so no filter can widen
 * it. Every filter scopes every number on the page; selecting a row in a split or a ranking filters to it.
 */
export function DashboardPage() {
  const user = useUser();
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS);
  const [bucketChoice, setBucketChoice] = useState<Bucket | null>(null);     // null: picked from the date span
  const params = useMemo(() => toParams(filters), [filters]);
  const query = useDashboard(params);
  const data = query.data;

  const bucket: Bucket = bucketChoice ?? autoBucket(data?.by_day ?? []);
  const columns = useMemo(() => toColumns(data?.by_day ?? [], bucket), [data, bucket]);
  const narrowed = activeCount(filters);
  const dateError = rangeError(filters);

  const setValue = (dimension: Dimension) => (value: string | null) =>
    setFilters((f) => ({ ...f, values: { ...f.values, [dimension]: value ?? ANY } }));
  const setDate = (key: 'period' | 'from' | 'to') => (value: string) => setFilters((f) => ({ ...f, [key]: value }));
  const selected = (dimension: Dimension) => (filters.values[dimension] === ANY ? null : filters.values[dimension]);

  /** The choices for one filter: every value the role has, plus the chosen one even if it has gone since. */
  const optionsFor = (dimension: Dimension) => {
    const values = new Set(data?.options[dimension] ?? []);
    if (filters.values[dimension] !== ANY) values.add(filters.values[dimension]);
    return [{ value: ANY, label: ANY_LABEL[dimension] },
      ...[...values].map((v) => ({ value: v, label: valueLabel(dimension, v) }))];
  };
  const singleRoute = (data?.options.route.length ?? 0) <= 1 && filters.values.route === ANY;
  const shownFilters = DIMENSIONS.filter((d) => !(d === 'route' && singleRoute));

  const scope = user.role === 'manager' ? 'every case' : 'the cases in your queue';

  return (
    <>
      <PageHeader title="Dashboard" subtitle={`Key figures over ${scope}. Updates every 30 seconds.`} />

      <section className={styles.filterPanel} aria-label="Filters">
        <div className={styles.filters}>
          <Select label="Received" value={filters.period} options={PERIODS} onValueChange={setDate('period')} />
          {filters.period === 'custom' && (
            <>
              <TextField label="From" type="date" value={filters.from} onChange={(e) => setDate('from')(e.target.value)}
                min={data?.date_range.first ?? undefined} max={data?.date_range.last ?? undefined} />
              <TextField label="To" type="date" value={filters.to} onChange={(e) => setDate('to')(e.target.value)}
                min={data?.date_range.first ?? undefined} max={data?.date_range.last ?? undefined} error={dateError} />
            </>
          )}
          {shownFilters.map((d) => (
            <Select key={d} label={DIMENSION_LABEL[d]} value={filters.values[d]} options={optionsFor(d)}
              onValueChange={(v) => setValue(d)(v)} />
          ))}
        </div>
        <div className={styles.filterFooter}>
          <p className={styles.caption} aria-live="polite">
            {data && `${count(data.total)} cases. ${periodText(data.applied, data.date_range)}`}
            {narrowed > 0 && ` ${narrowed === 1 ? '1 filter' : `${narrowed} filters`} on.`}
          </p>
          {narrowed > 0 && (
            <Button variant="ghost" icon={FilterX} onClick={() => setFilters(DEFAULT_FILTERS)}>Clear filters</Button>
          )}
        </div>
      </section>

      {query.isPending && <Spinner label="Loading the dashboard" />}
      {query.isError && !data && <Alert tone="error">{query.error.message}</Alert>}
      {query.isError && data && (
        <Alert tone="warning">Could not refresh the dashboard ({query.error.message}). Showing the last numbers.</Alert>
      )}

      {data && (
        <div className={styles.body} aria-busy={query.isPlaceholderData} data-stale={query.isPlaceholderData || undefined}>
          {data.total === 0 ? (
            <EmptyState title="No cases match">
              {narrowed > 0 ? 'Try another date range, or clear the filters.' : 'No complaints have been processed yet.'}
            </EmptyState>
          ) : (
            <Board data={data} filters={filters} bucket={bucket} columns={columns} onBucket={setBucketChoice}
              selected={selected} setValue={setValue} />
          )}
        </div>
      )}
    </>
  );
}

interface BoardProps {
  data: Dashboard;
  filters: DashboardFilters;
  bucket: Bucket;
  columns: ReturnType<typeof toColumns>;
  onBucket: (bucket: Bucket) => void;
  selected: (dimension: Dimension) => string | null;
  setValue: (dimension: Dimension) => (value: string | null) => void;
}

function Board({ data, filters, bucket, columns, onBucket, selected, setValue }: BoardProps) {
  const { kpis, previous } = data;
  const trend = (pick: (d: DailyKpis) => number) =>
    fillDays(data.daily, pick, data.applied.date_from, data.applied.date_to);
  const against = comparedWith(filters, previous);
  const onTime = kpis.open ? share(kpis.open - kpis.overdue, kpis.open) : 100;
  const slices = (dimension: 'priority' | 'language', colors: Record<string, string>) =>
    Object.entries(data.breakdowns[dimension])
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([value, n]) => ({ value, n, label: valueLabel(dimension, value), color: colors[value] ?? 'var(--text-3)' }));

  return (
    <>
      <section className={styles.scorecards} aria-label="Scorecards">
        <Scorecard label="Complaints received" value={count(data.total)} kind="bars"
          note={`${share(kpis.auto_sent, data.total)}% resolved with no person involved`}
          points={trend((d) => d.received)} format={count}
          change={previous && delta(data.total, previous.total, 'neutral')} comparedWith={against} />
        <Scorecard label="Waiting for a person" value={count(kpis.waiting)}
          note={kpis.awaiting_customer ? `${count(kpis.awaiting_customer)} more waiting for the customer`
            : 'In the approval and fraud queues'}
          points={trend((d) => d.waiting)} format={count}
          change={previous && delta(kpis.waiting, previous.kpis.waiting, 'down')} comparedWith={against} />
        <Scorecard label="Past the acknowledgement time" value={count(kpis.overdue)}
          note={`Of ${count(kpis.open)} open cases`}
          points={trend((d) => d.overdue)} format={count}
          change={previous && delta(kpis.overdue, previous.kpis.overdue, 'down')} comparedWith={against} />
        <Scorecard label="Refunds sent" value={money(kpis.refund_sent_myr)}
          note={`${money(kpis.refund_waiting_myr)} more waiting for approval`}
          points={trend((d) => d.refund_sent_myr)} format={money}
          change={previous && delta(kpis.refund_sent_myr, previous.kpis.refund_sent_myr, 'neutral')}
          comparedWith={against} />
      </section>

      <section className={styles.rates} aria-label="Rates and splits">
        <Gauge label="Automation rate" value={share(kpis.auto_sent, data.total)} target={TARGETS.automation}
          detail={`${count(kpis.auto_sent)} of ${count(data.total)} cases resolved with no person involved`} />
        <Gauge label="Acknowledged on time" value={onTime} target={TARGETS.onTime}
          detail={kpis.open ? `${count(kpis.overdue)} of ${count(kpis.open)} open cases are past the time allowed`
            : 'No open cases'} />
        <Donut label="Priority" slices={slices('priority', PRIORITY_COLOR)} selected={selected('priority')}
          onSelect={setValue('priority')} />
        <Donut label="Reply language" slices={slices('language', LANGUAGE_COLOR)} selected={selected('language')}
          onSelect={setValue('language')} />
      </section>

      <Card title="Complaints received over time" className={styles.volume}>
        <div className={styles.volumeHead}>
          <p className={styles.caption}>By the day each complaint arrived, coloured by where the case is now.</p>
          <div className={styles.bucket} role="group" aria-label="Columns">
            {BUCKETS.map((b) => (
              <button key={b.value} type="button" aria-pressed={bucket === b.value} onClick={() => onBucket(b.value)}>
                {b.label}
              </button>
            ))}
          </div>
        </div>
        <VolumeChart columns={columns} bucket={bucket} />
      </Card>

      <div className={styles.rankings}>
        <RankedTable title="Top categories" nameHeading="Category" total={data.total} extraHeading="Refunds sent"
          rows={data.categories.map((c) => ({ value: c.category, label: valueLabel('category', c.category), n: c.n,
            extra: money(c.refund_sent_myr) }))}
          selected={selected('category')} onSelect={setValue('category')} />
        <RankedTable title="Top channels" nameHeading="Channel" total={data.total}
          rows={Object.entries(data.breakdowns.channel).map(([value, n]) => ({ value, n,
            label: valueLabel('channel', value) }))}
          selected={selected('channel')} onSelect={setValue('channel')} />
      </div>

      <OutcomeByCategory categories={data.categories} />

      {data.people && <PeopleCard people={data.people} />}
    </>
  );
}
