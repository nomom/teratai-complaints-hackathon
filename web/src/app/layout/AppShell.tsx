import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router';

import { FlashOutlet, useFlash } from '../providers/FlashProvider';
import { ThemeSwitch } from '../providers/ThemeSwitch';
import styles from './AppShell.module.css';
import { Sidebar } from './Sidebar';

/** Mobile first: the sidebar stacks above the content; from 960px it is a fixed column on the left. */
export function AppShell() {
  const { pathname } = useLocation();
  const { clear } = useFlash();
  useEffect(() => clear, [pathname, clear]);          // a confirmation belongs to the page it was shown on

  return (
    <div className={styles.shell}>
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
