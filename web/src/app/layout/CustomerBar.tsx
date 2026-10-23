import { clsx } from 'clsx';
import { NavLink } from 'react-router';

import { useUser } from '@/features/auth/AuthProvider';

import { pagesFor } from '../navigation';
import { AccountMenu } from './AccountMenu';
import { OrbMark } from './OrbMark';
import styles from './CustomerBar.module.css';

/** The customer's app bar: their bank, their pages, and who is signed in. Profile and Transactions live in the
 *  account menu, as in the staff sidebar. */
export function CustomerBar() {
  const user = useUser();
  const pages = pagesFor(user.role).filter((p) => p.section !== 'Account');

  return (
    <header className={styles.bar}>
      <div className={styles.inner}>
        <p className={styles.brand}>
          <OrbMark size={24} />
          Teratai Bank
        </p>

        <nav aria-label="Pages" className={styles.nav}>
          <ul>
            {pages.map(({ key, path, title, icon: Icon }) => (
              <li key={key}>
                <NavLink to={path} className={({ isActive }) => clsx(styles.link, isActive && styles.active)}>
                  <Icon aria-hidden />
                  {title}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className={styles.account}>
          <AccountMenu compact />
        </div>
      </div>
    </header>
  );
}
