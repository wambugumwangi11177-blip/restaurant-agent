/** A browser-side convenience (a hidden banner, a skipped tour): never relied on, and never throws when storage is blocked or full. */
export function readFlag(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

export function writeFlag(key: string, value: string): void {
  try { window.localStorage.setItem(key, value); } catch { /* the choice just lasts until the page is reloaded */ }
}
