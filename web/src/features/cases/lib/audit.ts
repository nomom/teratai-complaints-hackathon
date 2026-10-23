/** An audit detail as one line: JSON objects become "key: value" pairs (long replies are left out), text stays. */
export function readable(detail: string): string {
  let text = detail;
  try {
    const value: unknown = JSON.parse(detail);
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      text = Object.entries(value as Record<string, unknown>)
        .filter(([key, v]) => key !== 'reply_text' && key !== 'text' && v !== null && v !== '' && v !== false)
        .map(([key, v]) => `${key}: ${Array.isArray(v) ? v.join('; ') : String(v)}`)
        .join(' · ');
    }
  } catch {
    // plain text, e.g. a reason or the reply that was sent
  }
  return text.length > 160 ? `${text.slice(0, 157)}...` : text;
}
