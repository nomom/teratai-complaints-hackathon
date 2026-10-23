import { clsx } from 'clsx';
import { NavLink } from 'react-router';

import { useUser } from '@/features/auth/AuthProvider';
import { StatusBadge } from '@/features/cases/components/Badges';
import { useCounts } from '@/features/cases/hooks';
import { FILTER_STATUSES } from '@/features/cases/lib/status';

import { pagesFor, SECTIONS } from '../navigation';
import { AccountMenu } from './AccountMenu';
import styles from './Sidebar.module.css';

export function Sidebar() {
  const user = useUser();
  const pages = pagesFor(user.role);
  const staff = user.role !== 'customer';
  const counts = useCounts(staff).data ?? {};
  const shown = [...FILTER_STATUSES, 'SENT' as const].filter((s) => counts[s]);

  return (
    <aside className={styles.sidebar}>
      <p className={styles.brand}>
        <span className={styles.dot} aria-hidden />
        Teratai Ops
      </p>

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
