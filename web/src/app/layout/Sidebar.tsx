import { clsx } from 'clsx';
import { LogOut } from 'lucide-react';
import { NavLink, useNavigate } from 'react-router';

import { Badge, Button } from '@/components/ui';
import { useUser, useAuth } from '@/features/auth/AuthProvider';
import { ROLE_LABEL } from '@/features/auth/types';
import { StatusBadge } from '@/features/cases/components/Badges';
import { useCounts } from '@/features/cases/hooks';
import { FILTER_STATUSES } from '@/features/cases/lib/status';

import { pagesFor, SECTIONS } from '../navigation';
import { ThemeSwitch } from '../providers/ThemeSwitch';
import styles from './Sidebar.module.css';

export function Sidebar() {
  const user = useUser();
  const { signOut } = useAuth();
  const navigate = useNavigate();
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

      <div className={styles.profile}>
        <p className={styles.name}>{user.full_name}</p>
        <Badge tone="accent">{ROLE_LABEL[user.role]}</Badge>
        <p className={styles.sub}>Signed in as {user.username}</p>
      </div>

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

      <Button icon={LogOut} block onClick={() => {
        signOut();
        navigate('/sign-in', { replace: true });
      }}>
        Log out
      </Button>
      <div className={styles.theme}>
        <ThemeSwitch />
      </div>
    </aside>
  );
}
