/** RM 1,234.56: always two decimals; "-" when there is no amount. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  const sign = value < 0 ? '-' : '';
  return `${sign}RM ${Math.abs(value).toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** DUPLICATE_CHARGE -> Duplicate charge; ATM_NOT_DISPENSED -> ATM not dispensed. */
export function nice(code: string | null | undefined): string {
  if (!code) return '-';
  const text = code.replace(/_/g, ' ').toLowerCase();
  return (text.charAt(0).toUpperCase() + text.slice(1)).replace(/\batm\b/gi, 'ATM').replace(/\bllm\b/gi, 'LLM');
}

/** 2d 3h, 4h 05m or 12m, for a duration in milliseconds (the sign is ignored). */
export function duration(ms: number): string {
  const minutes = Math.floor(Math.abs(ms) / 60000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${String(mins).padStart(2, '0')}m`;
  return `${mins}m`;
}

/** "2026-09-30 18:00:00" -> Date (local time, as stored). */
export function parseStamp(stamp: string | null | undefined): Date | null {
  if (!stamp) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(stamp);
  if (!match) return null;
  const [, y, mo, d, h, mi, s] = match;
  return new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s ?? 0));
}

// Spelled out rather than Intl: browsers disagree on short months ("Sep" or "Sept")
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
  'November', 'December'];

/** "2002-02-07" or "2026-09-22 18:49:54" -> 7 Feb 2002 / 22 Sep 2026; "-" when there is no date. */
export function day(stamp: string | null | undefined): string {
  const match = stamp ? /^(\d{4})-(\d{2})-(\d{2})/.exec(stamp) : null;
  if (!match) return '-';
  const [, y, m, d] = match;
  return `${Number(d)} ${MONTHS[Number(m) - 1].slice(0, 3)} ${y}`;
}

/** "2026-09-22 18:49:54" -> September 2026. */
export function monthOf(stamp: string): string {
  const [y, m] = stamp.split('-');
  return `${MONTHS[Number(m) - 1]} ${y}`;
}

/** Chan Zhi Hao -> CH, Nur Farah binti Rahman -> NR: first and last capitalised words (skips bin, a/l, ...). */
export function initials(name: string): string {
  const words = name.split(/\s+/).filter((w) => /^[A-Z]/.test(w));
  if (!words.length) return name.trim().charAt(0).toUpperCase();
  return (words[0][0] + (words.length > 1 ? words[words.length - 1][0] : '')).toUpperCase();
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
