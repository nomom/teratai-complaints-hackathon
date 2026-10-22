import { ApiError } from '@/lib/apiClient';
import { sleep } from '@/lib/format';

export const WORKER_TIMEOUT_MS = 30000;

/**
 * Poll until the worker has (re)processed a case: it exists, and its updated_at moved on from `before`.
 * A 404 means "not processed yet"; any other error (e.g. 403: routed to another team) ends the wait at once.
 * Resolves null if the worker did not answer in time.
 */
export async function waitForWorker<T extends { updated_at: string }>(
  load: () => Promise<T>,
  before?: string,
  { interval = 500, timeout = WORKER_TIMEOUT_MS } = {},
): Promise<T | null> {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    try {
      const value = await load();
      if (value.updated_at !== before) return value;
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 404) throw e;
    }
    await sleep(interval);
  }
  return null;
}
