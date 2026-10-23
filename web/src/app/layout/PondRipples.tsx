import { clsx } from 'clsx';
import { useEffect, useState } from 'react';

import styles from './PondRipples.module.css';
import { WaterLines } from './WaterLines';

/** Where each lily pad floats: position, size (px), turn and how long one slow bob takes. */
const PADS: Record<'hero' | 'ambient', { x: string; y: string; size: number; turn: number; period: number }[]> = {
  hero: [
    { x: '12%', y: '22%', size: 150, turn: 20, period: 26 },
    { x: '22%', y: '70%', size: 96, turn: 140, period: 31 },
    { x: '8%', y: '86%', size: 64, turn: 260, period: 23 },
    { x: '84%', y: '18%', size: 120, turn: 300, period: 29 },
    { x: '91%', y: '48%', size: 72, turn: 80, period: 34 },
    { x: '70%', y: '88%', size: 110, turn: 200, period: 27 },
  ],
  ambient: [
    { x: '94%', y: '14%', size: 110, turn: 300, period: 32 },
    { x: '88%', y: '84%', size: 140, turn: 120, period: 36 },
    { x: '97%', y: '58%', size: 64, turn: 40, period: 28 },
  ],
};

/** A lily pad: a disc with its notch. */
function Pad() {
  return (
    <svg viewBox="0 0 100 100" className={styles.padShape}>
      <path d="M50 50 L54 2 A48 48 0 1 1 30 6.5 Z" fill="var(--pad)" stroke="var(--pad-edge)" strokeWidth="1.2"
        strokeLinejoin="round" />
    </svg>
  );
}

/** A CSS custom property's value on <html> right now. WebGL can't read var(--x), so this reads it again whenever
 *  the theme or the role on <html> changes. */
function useRootStyle(name: string, fallback: string): string {
  const [value, setValue] = useState(fallback);
  useEffect(() => {
    const read = () => setValue(getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback);
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-role'] });
    return () => observer.disconnect();
  }, [name, fallback]);
  return value;
}

/** The background is a lotus pond: soft pools of colour under the surface, the surface itself moving (wave
 *  lines in the role's colour), and lily pads floating on it. `hero` (sign-in) is the whole pond and leans away from the pointer; `ambient`
 *  (inside the app) is calm and faint, and a click sends a ripple across it. Decorative; with reduced motion the
 *  surface stands still. */
export function PondRipples({ variant }: { variant: 'hero' | 'ambient' }) {
  const hero = variant === 'hero';
  const line = useRootStyle('--primary', '#0A6AA8');
  return (
    <div className={clsx(styles.pond, hero ? styles.heroPond : styles.ambientPond)} aria-hidden>
      <span className={clsx(styles.pool, styles.poolA)} />
      <span className={clsx(styles.pool, styles.poolB)} />
      <span className={clsx(styles.pool, styles.poolC)} />
      <WaterLines className={styles.surface} color={line} followPointer={hero}
        spacing={hero ? 26 : 34} amplitude={hero ? 26 : 18} speed={hero ? 0.6 : 0.4} opacity={hero ? 0.38 : 0.22} />
      {PADS[variant].map((p) => (
        <span key={`${p.x}${p.y}`} className={styles.pad} style={{
          left: p.x, top: p.y, width: p.size, height: p.size,
          ['--turn' as string]: `${p.turn}deg`, ['--bob' as string]: `${p.period}s`,
        }}>
          <Pad />
        </span>
      ))}
    </div>
  );
}
