import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router';

import { useUser } from '@/features/auth/AuthProvider';

import { FlashOutlet, useFlash } from '../providers/FlashProvider';
import { ThemeSwitch } from '../providers/ThemeSwitch';
import styles from './AppShell.module.css';
import { CustomerBar } from './CustomerBar';
import { PondRipples } from './PondRipples';
import { Sidebar } from './Sidebar';

/** Staff work at a desk: a sidebar in their role's colour (mobile first, it stacks above the content; from 960px
 *  it is a fixed column). A customer gets their bank's app instead: a top bar and one centred column. */
export function AppShell() {
  const { pathname } = useLocation();
  const { clear } = useFlash();
  const { role } = useUser();
  useEffect(() => clear, [pathname, clear]);          // a confirmation belongs to the page it was shown on

  useEffect(() => {                                    // the role's colours (tokens.css, [data-role])
    document.documentElement.dataset.role = role;
    return () => {
      delete document.documentElement.dataset.role;
    };
  }, [role]);

  if (role === 'customer') {
    return (
      <div className={styles.customerShell}>
        <PondRipples variant="ambient" />
        <CustomerBar />
        <main className={styles.customerMain} id="main">
          <FlashOutlet />
          <Outlet />
        </main>
      </div>
    );
  }

  return (
    <div className={styles.shell}>
      <PondRipples variant="ambient" />
      <Sidebar />
      <main className={styles.main} id="main">
        <div className={styles.topBar}>
          <ThemeSwitch />
        </div>
        <FlashOutlet />
        <Outlet />
      </main>
    </div>
  );
}
