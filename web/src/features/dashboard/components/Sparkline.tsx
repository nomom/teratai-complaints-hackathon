import type { PointerEvent } from 'react';

import styles from './charts.module.css';

interface SparklineProps {
  points: { day: string; value: number }[];
  kind?: 'line' | 'bars';
  /** The point under the pointer, or null. */
  active: number | null;
  onActive: (index: number | null) => void;
}

const TOP = 6;          // headroom above the highest point, in viewBox units (of 100)

/**
 * A small trend under a scorecard figure: one value per day, no axes. It stretches to its box, so lines keep a 2px
 * stroke whatever the width. The scorecard prints the value under the pointer; the full numbers are in the
 * volume chart's table.
 */
export function Sparkline({ points, kind = 'line', active, onActive }: SparklineProps) {
  const n = points.length;
  if (n === 0) return <div className={styles.sparkline} aria-hidden />;
  const max = Math.max(...points.map((p) => p.value), 1);
  const y = (v: number) => 100 - (v / max) * (100 - TOP);
  const track = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    onActive(Math.min(n - 1, Math.max(0, Math.floor(((e.clientX - box.left) / box.width) * n))));
  };
  const line = points.map((p, i) => `${i + 0.5},${y(p.value)}`).join(' ');

  return (
    <svg className={styles.sparkline} viewBox={`0 0 ${n} 100`} preserveAspectRatio="none" aria-hidden
      onPointerMove={track} onPointerLeave={() => onActive(null)}>
      {kind === 'bars' ? (
        points.map((p, i) => (
          <rect key={p.day} x={i + 0.15} width={0.7} y={y(p.value)} height={100 - y(p.value)}
            className={i === active ? styles.sparkBarActive : styles.sparkBar} />
        ))
      ) : (
        <>
          <polygon points={`0.5,100 ${line} ${n - 0.5},100`} className={styles.sparkArea} />
          <polyline points={line} className={styles.sparkLine} vectorEffect="non-scaling-stroke" />
        </>
      )}
      {active !== null && (
        <line x1={active + 0.5} x2={active + 0.5} y1={0} y2={100} className={styles.sparkCursor}
          vectorEffect="non-scaling-stroke" />
      )}
    </svg>
  );
}
