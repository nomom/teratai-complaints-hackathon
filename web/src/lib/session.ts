/** The sign-in token for this browser tab. sessionStorage can be unavailable (private mode), so every access is guarded. */
const KEY = 'teratai.token';

export const session = {
  get(): string | null {
    try {
      return sessionStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set(token: string): void {
    try {
      sessionStorage.setItem(KEY, token);
    } catch {
      /* the session still works until the tab reloads */
    }
  },
  clear(): void {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* nothing stored */
    }
  },
};
