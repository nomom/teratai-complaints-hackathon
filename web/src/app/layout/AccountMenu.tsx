import { clsx } from 'clsx';
import { ChevronsUpDown, LogOut } from 'lucide-react';
import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router';

import { Avatar, Popover } from '@/components/ui';
import { useAuth, useUser } from '@/features/auth/AuthProvider';
import { ROLE_LABEL } from '@/features/auth/types';

import { pagesFor } from '../navigation';
import { ThemeSwitch } from '../providers/ThemeSwitch';
import styles from './AccountMenu.module.css';

/** Who is signed in: at the bottom of the staff sidebar (opens upward) or in the customer's top bar (opens downward,
 *  `compact`). It holds the role's account pages, the theme and Log out. */
export function AccountMenu({ compact = false }: { compact?: boolean }) {
  const user = useUser();
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const pages = pagesFor(user.role).filter((p) => p.section === 'Account');

  const trigger = (
    <button type="button" className={clsx(styles.trigger, compact && styles.compact)} aria-label={`${user.full_name}, account menu`}>
      <Avatar name={user.full_name} />
      <span className={styles.who}>
        <span className={styles.name}>{user.full_name}</span>
        <span className={styles.role}>{ROLE_LABEL[user.role]}</span>
      </span>
      <ChevronsUpDown className={styles.chevron} aria-hidden />
    </button>
  );

  return (
    <Popover trigger={trigger} open={open} onOpenChange={setOpen} side={compact ? 'bottom' : 'top'} className={styles.menu}>
      <div className={styles.header}>
        <p className={styles.headerName}>{user.full_name}</p>
        <p className={styles.headerSub}>Signed in as {user.username}</p>
      </div>

      {pages.length > 0 && (
        <nav aria-label="Account" className={styles.group}>
          <ul>
            {pages.map(({ key, path, title, icon: Icon }) => (
              <li key={key}>
                <NavLink to={path} onClick={() => setOpen(false)}
                  className={({ isActive }) => clsx(styles.item, isActive && styles.active)}>
                  <Icon aria-hidden />
                  {title}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      )}

      <div className={clsx(styles.group, styles.theme)}>
        <ThemeSwitch />
      </div>

      <div className={styles.group}>
        <button type="button" className={styles.item} onClick={() => {
          setOpen(false);
          signOut();
          navigate('/sign-in', { replace: true });
        }}>
          <LogOut aria-hidden />
          Log out
        </button>
      </div>
    </Popover>
  );
}
