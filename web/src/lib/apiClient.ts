import { session } from './session';

/** Base path of the FastAPI app. The Vite dev server proxies /api to it (see vite.config.ts). */
export const API_BASE = '/api';

/** A refused request: the HTTP status plus whatever FastAPI put in `detail` (a string, or an object with a code). */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(messageOf(detail) ?? `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }

  /** A field of an object `detail`, e.g. `code`, `route` or `problems`. */
  field<T = unknown>(name: string): T | undefined {
    return typeof this.detail === 'object' && this.detail !== null
      ? ((this.detail as Record<string, unknown>)[name] as T)
      : undefined;
  }
}

function messageOf(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return 'Some fields are missing or invalid.';
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>;
    if (typeof d.message === 'string') return d.message;
    if (typeof d.error === 'string') return d.error;
  }
  return undefined;
}

type Listener = (error: ApiError) => void;
const unauthorizedListeners = new Set<Listener>();

/** Called when the API says the session is no longer valid (401), so the app can sign out. */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  signal?: AbortSignal;
}

export async function apiRequest<T>(path: string, { method = 'GET', body, signal }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = session.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = new ApiError(response.status, payload?.detail ?? payload);
    if (response.status === 401 && token) unauthorizedListeners.forEach((listener) => listener(error));
    throw error;
  }
  return payload as T;
}
