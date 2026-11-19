/** Client-side PIN shell unlock (sessionStorage — dies with the WebView tab). */

export const APP_LOCK_IDLE_MS = 15 * 60 * 1000;
const UNLOCK_KEY = "app_pin_unlocked";
const ACTIVITY_KEY = "app_last_activity";

export function clearPinUnlock(): void {
  try {
    sessionStorage.removeItem(UNLOCK_KEY);
    sessionStorage.removeItem(ACTIVITY_KEY);
  } catch {
    /* private mode */
  }
}

export function markPinUnlocked(): void {
  try {
    sessionStorage.setItem(UNLOCK_KEY, "1");
    touchActivity();
  } catch {
    /* private mode */
  }
}

export function isPinUnlocked(): boolean {
  try {
    return sessionStorage.getItem(UNLOCK_KEY) === "1";
  } catch {
    return false;
  }
}

export function touchActivity(): void {
  try {
    sessionStorage.setItem(ACTIVITY_KEY, String(Date.now()));
  } catch {
    /* private mode */
  }
}

export function idleLockDue(): boolean {
  try {
    const raw = sessionStorage.getItem(ACTIVITY_KEY);
    if (!raw) return true;
    const last = Number(raw);
    if (!Number.isFinite(last)) return true;
    return Date.now() - last > APP_LOCK_IDLE_MS;
  } catch {
    return true;
  }
}