import { clsx } from 'clsx';
import { NavLink } from 'react-router';

import { useUser } from '@/features/auth/AuthProvider';
import type { Role } from '@/features/auth/types';
import { StatusBadge } from '@/features/cases/components/Badges';
import { useCounts } from '@/features/cases/hooks';
import { FILTER_STATUSES } from '@/features/cases/lib/status';

import { pagesFor, SECTIONS } from '../navigation';
import { AccountMenu } from './AccountMenu';
import { OrbMark } from './OrbMark';
import styles from './Sidebar.module.css';

/** Each staff role works at its own desk: its name and job sit at the top, in the role's colour. */
const DESK: Record<Exclude<Role, 'customer'>, { name: string; job: string }> = {
  officer: { name: 'Approval desk', job: 'Cases the agent may not send alone wait here for you.' },
  fraud: { name: 'Fraud desk', job: 'Held for investigation. Nothing reaches the customer until you act.' },
  manager: { name: 'Operations', job: 'Every queue, the numbers, and who did what.' },
};

export function Sidebar() {
  const user = useUser();
  const pages = pagesFor(user.role);
  const staff = user.role !== 'customer';
  const counts = useCounts(staff).data ?? {};
  const shown = [...FILTER_STATUSES, 'SENT' as const].filter((s) => counts[s]);
  const desk = user.role === 'customer' ? null : DESK[user.role];

  return (
    <aside className={styles.sidebar}>
      <p className={styles.brand}>
        <OrbMark />
        Teratai Bank
      </p>

      {desk && (
        <div className={styles.desk}>
          <p className={styles.deskName}>{desk.name}</p>
          <p className={styles.deskJob}>{desk.job}</p>
        </div>
      )}

      <nav aria-label="Pages">
        {SECTIONS.filter((section) => pages.some((p) => p.section === section)).map((section) => (
          <div key={section} className={styles.section}>
            <p className={styles.sectionTitle}>{section}</p>
            <ul>
              {pages.filter((p) => p.section === section).map(({ key, path, title, icon: Icon }) => (
                <li key={key}>
                  <NavLink to={path} className={({ isActive }) => clsx(styles.link, isActive && styles.active)}>
                    <Icon aria-hidden />
                    {title}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {staff && shown.length > 0 && (
        <div className={styles.counts}>
          <p className={styles.sectionTitle}>Cases you can see</p>
          <ul>
            {shown.map((status) => (
              <li key={status}>
                <StatusBadge status={status} />
                <span className={styles.count}>{counts[status]!.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className={styles.account}>
        <AccountMenu />
      </div>
    </aside>
  );
}
