import { clsx } from 'clsx';
import { CircleX, MessageSquareWarning } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import { Alert, Badge, EmptyState, PageHeader, Select, Spinner, TextField } from '@/components/ui';
import { day, money, monthOf } from '@/lib/format';

import styles from '../components/account.module.css';
import { useProfile, useStatement } from '../hooks';
import type { BankAccount, Transaction } from '../types';

const ALL = 'all';

const accountLabel = (a: BankAccount) => (a.card_last4 ? `${a.product} ending ${a.card_last4}` : `${a.product} ${a.account_id}`);

/** The line a customer recognises: a fee by what it was for, anything else by who was paid or who paid. */
const titleOf = (t: Transaction) => (t.channel === 'Fee' && t.description ? t.description : t.merchant_or_counterparty);

const total = (rows: Transaction[], direction: 'CR' | 'DR') =>
  rows.filter((t) => t.direction === direction && t.status !== 'Failed').reduce((sum, t) => sum + t.amount_myr, 0);

export function TransactionsPage() {
  const statement = useStatement();
  const profile = useProfile();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState('');

  const error = statement.error ?? profile.error;
  if (error) {
    return (
      <>
        <PageHeader title="Transactions" />
        <Alert tone="error">{error.message}</Alert>
      </>
    );
  }
  if (!statement.data || !profile.data) {
    return (
      <>
        <PageHeader title="Transactions" />
        <Spinner label="Loading your transactions" />
      </>
    );
  }

  const { accounts } = profile.data;
  const { as_of: asOf, report_window_days: windowDays, transactions } = statement.data;
  const wanted = params.get('account');
  const selected = accounts.some((a) => a.account_id === wanted) ? wanted! : ALL;
  const labels = Object.fromEntries(accounts.map((a) => [a.account_id, accountLabel(a)]));
  const needle = search.trim().toLowerCase();
  const rows = transactions.filter((t) =>
    (selected === ALL || t.account_id === selected)
    && (!needle || [titleOf(t), t.merchant_or_counterparty, t.description, t.txn_id, t.channel]
      .some((field) => field.toLowerCase().includes(needle))));

  const months = new Map<string, Transaction[]>();
  rows.forEach((t) => {
    const key = t.txn_time.slice(0, 7);
    months.set(key, [...(months.get(key) ?? []), t]);
  });

  return (
    <>
      <PageHeader title="Transactions"
        subtitle={`Up to ${day(asOf)}. You can report a problem with anything from the last ${windowDays} days.`} />

      <div className={styles.toolbar}>
        <Select label="Account" value={selected}
          options={[{ value: ALL, label: 'All accounts' }, ...accounts.map((a) => ({ value: a.account_id, label: accountLabel(a) }))]}
          onValueChange={(value) => setParams(value === ALL ? {} : { account: value }, { replace: true })} />
        <TextField label="Search" type="search" placeholder="Merchant, person or reference" value={search}
          onChange={(e) => setSearch(e.target.value)} />
      </div>

      <p className={styles.summary} aria-live="polite">
        <span>{rows.length} {rows.length === 1 ? 'transaction' : 'transactions'}</span>
        <span>Money in <strong className={styles.credit}>{money(total(rows, 'CR'))}</strong></span>
        <span>Money out <strong>{money(total(rows, 'DR'))}</strong></span>
      </p>

      {rows.length === 0 ? (
        <EmptyState title="No transactions match">Try another account, or clear the search.</EmptyState>
      ) : (
        <div className={styles.ledger}>
          {[...months].map(([key, monthRows]) => (
            <section key={key} aria-labelledby={`month-${key}`}>
              <h2 id={`month-${key}`} className={styles.month}>{monthOf(monthRows[0].txn_time)}</h2>
              <ul className={styles.txns}>
                {monthRows.map((t) => (
                  <TxnRow key={t.txn_id} txn={t} account={selected === ALL && accounts.length > 1 ? labels[t.account_id] : ''} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}

function TxnRow({ txn, account }: { txn: Transaction; account: string }) {
  const navigate = useNavigate();
  const credit = txn.direction === 'CR';
  const failed = txn.status === 'Failed';
  const title = titleOf(txn);
  const meta = [txn.channel, title === txn.description ? '' : txn.description, account].filter(Boolean).join(' · ');
  const amount = credit ? `+${money(txn.amount_myr)}` : money(-txn.amount_myr);
  const date = txn.txn_time.slice(8, 10);

  return (
    <li className={styles.txn}>
      <time className={styles.date} dateTime={txn.txn_time.replace(' ', 'T')}>
        <span className={styles.dateDay}>{Number(date)}</span>
        <span className={styles.dateMonth}>{monthOf(txn.txn_time).slice(0, 3)}</span>
        <span className="visually-hidden">{` ${day(txn.txn_time)}, ${txn.txn_time.slice(11, 16)}`}</span>
      </time>
      <div className={styles.txnMain}>
        <p className={styles.txnTitle}>{title}</p>
        <p className={styles.txnMeta}>{meta}</p>
        <p className={clsx(styles.txnMeta, styles.mono)}>
          {txn.txn_id}
          <span aria-hidden> · </span>
          {txn.txn_time.slice(11, 16)}
        </p>
      </div>
      <div className={styles.txnEnd}>
        <p className={clsx(styles.amount, credit && styles.credit, failed && styles.failed)}>{amount}</p>
        {failed && <Badge tone="error" icon={CircleX}>Failed</Badge>}
        {txn.reportable && (
          <button type="button" className={styles.report}
            aria-label={`Report a problem with ${title}, ${amount} on ${day(txn.txn_time)}`}
            onClick={() => navigate('/new-complaint', { state: { txn } })}>
            <MessageSquareWarning aria-hidden />
            Report
          </button>
        )}
      </div>
    </li>
  );
}
