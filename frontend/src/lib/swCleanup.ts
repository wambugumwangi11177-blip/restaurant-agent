/** Drop stale PWA caches and legacy service workers after LEVIII shell cutover. */
const CURRENT_CACHE = "leviii-v5";

export async function purgeLegacyPwaCaches(): Promise<void> {
  if (typeof window === "undefined" || !("caches" in window)) return;
  try {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CURRENT_CACHE).map((k) => caches.delete(k)));
  } catch {
    // best-effort
  }
}

export async function registerLeviiiServiceWorker(): Promise<void> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  try {
    await purgeLegacyPwaCaches();
    const regs = await navigator.serviceWorker.getRegistrations();
    for (const reg of regs) {
      const url = reg.active?.scriptURL ?? reg.installing?.scriptURL ?? "";
      if (url && !url.includes("/sw.js")) {
        await reg.unregister();
      }
    }
    await navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" });
    const next = await navigator.serviceWorker.getRegistration();
    await next?.update();
  } catch {
    // PWA optional
  }
}

export const LEVIII_CACHE_NAME = CURRENT_CACHE;