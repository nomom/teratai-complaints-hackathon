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

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
