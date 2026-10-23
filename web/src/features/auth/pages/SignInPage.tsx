import * as RadixTabs from '@radix-ui/react-tabs';
import { useState } from 'react';
import { Navigate } from 'react-router';

import { OrbMark } from '@/app/layout/OrbMark';
import BlurText from '@/components/reactbits/BlurText';
import { PondRipples } from '@/app/layout/PondRipples';
import { homePath } from '@/app/navigation';
import { FlashOutlet } from '@/app/providers/FlashProvider';
import { ThemeSwitch } from '@/app/providers/ThemeSwitch';

import { useAuth } from '../AuthProvider';
import { LogInForm } from '../components/LogInForm';
import { SignUpForm } from '../components/SignUpForm';
import styles from './SignInPage.module.css';

export function SignInPage() {
  const { status, user } = useAuth();
  const [tab, setTab] = useState('log-in');
  if (status === 'signedIn' && user) return <Navigate to={homePath(user.role)} replace />;

  return (
    <div className={styles.page}>
      <div className={styles.glow} aria-hidden />
      <PondRipples variant="hero" />
      <div className={styles.topBar}>
        <ThemeSwitch />
      </div>
      <main className={styles.panel}>
        <OrbMark size={112} className={styles.mark} />
        <p className={styles.brand}>
          Teratai Bank
        </p>
        <h1 className={styles.title}>
          <BlurText text="Complaints Ops" animateBy="words" direction="top" trigger="load" className={styles.titleText} />
        </h1>
        <p className={styles.subtitle}>Sign in to work your queue, or to follow your complaints</p>
        <FlashOutlet />
        <RadixTabs.Root value={tab} onValueChange={setTab}>
          <RadixTabs.List className={styles.tabs} aria-label="Sign in or sign up">
            <RadixTabs.Trigger value="log-in" className={styles.tab}>
              Log in
            </RadixTabs.Trigger>
            <RadixTabs.Trigger value="sign-up" className={styles.tab}>
              Sign up (customers)
            </RadixTabs.Trigger>
          </RadixTabs.List>
          <RadixTabs.Content value="log-in" className={styles.card}>
            <LogInForm />
          </RadixTabs.Content>
          <RadixTabs.Content value="sign-up" className={styles.card}>
            <SignUpForm onSignedUp={() => setTab('log-in')} />
          </RadixTabs.Content>
        </RadixTabs.Root>
        <p className={styles.help}>
          Staff: officer1, fraud1 or manager1, password 1234. Customers: sign up first with your customer ID.
        </p>
      </main>
    </div>
  );
}
