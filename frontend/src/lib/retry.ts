// A backend restart, a deploy, or a dropped connection lasts a few seconds. Owners should see
// "Reconnecting…" and then their restaurant, not an error. Only failures that can pass on their own are
// retried: no response at all (network, or a proxy 502 without CORS headers), 5xx, 408 and 429. A 401, 403,
// 404 or 422 is a real answer and is returned at once.
import type { AxiosError } from "axios";

// Mutable so tests can shorten the waits. About 15 seconds in total covers a normal service restart.
export const RETRY = { delays: [1000, 2000, 4000, 8000] };

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export function isTransient(error: unknown): boolean {
  const status = (error as AxiosError | undefined)?.response?.status;
  if (status === undefined) return true;
  return status >= 500 || status === 408 || status === 429;
}

export async function withRetry<T>(
  run: () => Promise<T>,
  options: { tries?: number; onRetry?: (attempt: number) => void } = {},
): Promise<T> {
  const tries = options.tries ?? RETRY.delays.length + 1;
  let attempt = 0;
  for (;;) {
    try {
      return await run();
    } catch (error) {
      attempt += 1;
      if (attempt >= tries || !isTransient(error)) throw error;
      options.onRetry?.(attempt);
      await wait(RETRY.delays[Math.min(attempt - 1, RETRY.delays.length - 1)]);
    }
  }
}

// Last good copy of a page's data, kept for this browser session only. If the service stays down past the
// retries, the page shows this (marked as stale) instead of an error. Never used for a real refusal (401/404/...).
const CACHE_PREFIX = "demo-cache:";

function readCache<T>(key: string): T | null {
  try {
    const raw = window.sessionStorage.getItem(CACHE_PREFIX + key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeCache(key: string, value: unknown) {
  try {
    window.sessionStorage.setItem(CACHE_PREFIX + key, JSON.stringify(value));
  } catch {
    /* storage can be full or blocked: the page still works without it */
  }
}

export async function getWithFallback<D>(
  key: string,
  run: () => Promise<{ data: D }>,
  options: { tries?: number; onRetry?: (attempt: number) => void } = {},
): Promise<{ data: D; stale: boolean }> {
  try {
    const response = await withRetry(run, options);
    writeCache(key, response.data);
    return { data: response.data, stale: false };
  } catch (error) {
    const cached = isTransient(error) ? readCache<D>(key) : null;
    if (cached !== null) return { data: cached, stale: true };
    throw error;
  }
}
