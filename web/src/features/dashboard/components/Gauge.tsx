import { CircleAlert, CircleCheck } from 'lucide-react';

import { BAND_COLOR, BAND_LABEL, bandOf } from '../lib/kpi';
import styles from './charts.module.css';

interface GaugeProps {
  label: string;
  /** 0 to 100. */
  value: number;
  target: { good: number; fair: number };
  /** What the percentage is of, e.g. "512 of 1,240 cases". */
  detail: string;
}

const CX = 100;
const CY = 100;
const R = 80;

/** The point on the arc at `percent` along it, `out` units from the radius. */
function at(percent: number, out = 0): [number, number] {
  const angle = Math.PI * (1 - percent / 100);
  return [CX + (R + out) * Math.cos(angle), CY - (R + out) * Math.sin(angle)];
}

/**
 * A rate against its target: the arc fills to the value in red, amber or green by how far it is from the target,
 * a needle points at it, and a tick marks the target. The band is also said in words with an icon.
 */
export function Gauge({ label, value, target, detail }: GaugeProps) {
  const v = Math.min(Math.max(value, 0), 100);
  const band = bandOf(v, target);
  const Icon = band === 'good' ? CircleCheck : CircleAlert;
  const [tickIn, tickOut] = [at(target.good, -14), at(target.good, 14)];
  const needle = at(v, -26);

  return (
    <article className={styles.gaugeCard} aria-label={label}>
      <h2 className={styles.cardLabel}>{label}</h2>
      <div className={styles.gauge}>
        <svg viewBox="0 0 200 112" role="img" aria-label={`${v}%, target ${target.good}%`}>
          <path d={`M${CX - R} ${CY} A${R} ${R} 0 0 1 ${CX + R} ${CY}`} className={styles.gaugeTrack} />
          {v > 0 && (
            <path d={`M${CX - R} ${CY} A${R} ${R} 0 0 1 ${CX + R} ${CY}`} pathLength={100}
              strokeDasharray={`${v} 100`} className={styles.gaugeFill} style={{ stroke: BAND_COLOR[band] }} />
          )}
          <line x1={tickIn[0]} y1={tickIn[1]} x2={tickOut[0]} y2={tickOut[1]} className={styles.gaugeTick} />
          <line x1={CX} y1={CY} x2={needle[0]} y2={needle[1]} className={styles.gaugeNeedle} />
          <circle cx={CX} cy={CY} r={6} className={styles.gaugeHub} />
        </svg>
        <span className={styles.gaugeMin} aria-hidden>0%</span>
        <span className={styles.gaugeMax} aria-hidden>100%</span>
      </div>
      <p className={styles.gaugeValue}>{v}%</p>
      <p className={styles.gaugeBand}>
        <Icon aria-hidden style={{ color: BAND_COLOR[band] }} />
        {BAND_LABEL[band]} of {target.good}%
      </p>
      <p className={styles.scoreNote}>{detail}</p>
    </article>
  );
}
