/**
 * In-memory bearer-token store (FE-101).
 *
 * The access token used to live in localStorage, which any XSS could read
 * outright (persistent, cross-tab, forever). It now lives in a module-scoped
 * in-memory variable: still readable by the same XSS, but the token no longer
 * survives a page reload unless a session-scoped fallback copy exists, and it
 * never persists across browser sessions or tabs.
 *
 * TRADEOFF (honest scope note): sessionStorage is still readable by the same
 * XSS that could read localStorage, so this is a blast-radius reduction (the
 * token dies with the tab and never lands in persistent disk storage), NOT a
 * full fix. The real fix is HttpOnly, Secure, SameSite cookies set by the
 * backend, which requires backend auth changes and is out of scope here.
 *
 * The session fallback exists only because the app requires the session to
 * survive a page refresh (AuthContext rehydrates on mount; tests also rely on
 * persistence within a tab). The sessionStorage copy is consumed once at
 * rehydration; writes to it are best-effort (private-mode Safari can throw).
 */

const TOKEN_KEY = "access_token";
// Non-sensitive UI preference only — never the bearer token.
const UI_PREF_KEY = "sidebar_collapsed";

let _token: string | null = null;

function _sessionAvailable(): boolean {
  try {
    return typeof window !== "undefined" && !!window.sessionStorage;
  } catch {
    return false;
  }
}

export function getAccessToken(): string | null {
  if (_token !== null) return _token;
  // One-time rehydration from the session-scoped fallback (a page refresh
  // clears module state; sessionStorage keeps the tab's session alive).
  try {
    _token =
      typeof window !== "undefined"
        ? window.sessionStorage.getItem(TOKEN_KEY)
        : null;
  } catch {
    _token = null;
  }
  return _token;
}

export function setAccessToken(token: string | null): void {
  _token = token;
  try {
    if (typeof window !== "undefined" && window.sessionStorage) {
      if (token) {
        window.sessionStorage.setItem(TOKEN_KEY, token);
      } else {
        window.sessionStorage.removeItem(TOKEN_KEY);
      }
    }
  } catch {
    // Storage unavailable (private mode / disabled) — in-memory only.
  }
}

export function clearAccessToken(): void {
  setAccessToken(null);
}

/** Save a non-sensitive UI preference (allowed to use localStorage). */
export function setUiPreference(key: string, value: string): void {
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(`ui_pref_${key}`, value);
    }
  } catch {
    // best-effort only
  }
}

/** Read a non-sensitive UI preference. */
export function getUiPreference(key: string): string | null {
  try {
    return typeof window !== "undefined"
      ? window.localStorage.getItem(`ui_pref_${key}`)
      : null;
  } catch {
    return null;
  }
}
