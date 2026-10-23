import { ChevronRight, CircleCheck, CreditCard, Landmark } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { Alert, Avatar, Badge, Card, PageHeader, Spinner } from '@/components/ui';
import { day } from '@/lib/format';

import styles from '../components/account.module.css';
import { useProfile } from '../hooks';
import type { BankAccount, Profile } from '../types';

const LANGUAGE: Record<string, string> = { EN: 'English', MS: 'Bahasa Melayu' };

export function ProfilePage() {
  const query = useProfile();
  return (
    <>
      <PageHeader title="Profile" subtitle="Your details and accounts, as the bank holds them." />
      {query.isPending && <Spinner label="Loading your profile" />}
      {query.isError && <Alert tone="error">{query.error.message}</Alert>}
      {query.data && <ProfileView profile={query.data} />}
    </>
  );
}

function ProfileView({ profile }: { profile: Profile }) {
  return (
    <div className={styles.stack}>
      <section className={styles.identity} aria-label="Who you are">
        <Avatar name={profile.full_name} size="lg" />
        <div className={styles.identityText}>
          <h2 className={styles.identityName}>{profile.full_name}</h2>
          <p className={styles.identityMeta}>
            <span className={styles.mono}>{profile.customer_id}</span>
            <span aria-hidden> · </span>
            {profile.segment} customer since {day(profile.customer_since)}
          </p>
        </div>
      </section>

      <div className={styles.columns}>
        <Card title="Personal details">
          <dl className={styles.details}>
            <Detail label="Full name">{profile.full_name}</Detail>
            <Detail label="Customer ID"><span className={styles.mono}>{profile.customer_id}</span></Detail>
            <Detail label="Date of birth">{day(profile.date_of_birth)}</Detail>
            <Detail label="Email">{profile.email}</Detail>
            <Detail label="City">{`${profile.city}, ${profile.state}`}</Detail>
            <Detail label="Preferred language">{LANGUAGE[profile.preferred_language] ?? profile.preferred_language}</Detail>
          </dl>
          <p className={styles.note}>To change these details, call us or visit any branch.</p>
        </Card>

        <Card title={`Your accounts (${profile.accounts.length})`}>
          <ul className={styles.accounts}>
            {profile.accounts.map((account) => (
              <AccountRow key={account.account_id} account={account} />
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.detail}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

const isCard = (product: string) => product.toLowerCase().includes('card');

function AccountRow({ account }: { account: BankAccount }) {
  const Icon = isCard(account.product) ? CreditCard : Landmark;
  return (
    <li>
      <Link to={`/transactions?account=${encodeURIComponent(account.account_id)}`} className={styles.account}
        aria-label={`${account.product} ${account.account_id}: view transactions`}>
        <span className={styles.accountIcon} aria-hidden><Icon /></span>
        <span className={styles.accountText}>
          <span className={styles.accountName}>{account.product}</span>
          <span className={styles.accountMeta}>
            <span className={styles.mono}>{account.account_id}</span>
            {account.card_last4 && <> · card ending {account.card_last4}</>}
            {' · '}opened {day(account.open_date)}
          </span>
        </span>
        {account.status === 'Active'
          ? <Badge tone="success" icon={CircleCheck}>Active</Badge>
          : <Badge tone="neutral">{account.status}</Badge>}
        <ChevronRight className={styles.accountChevron} aria-hidden />
      </Link>
    </li>
  );
}
