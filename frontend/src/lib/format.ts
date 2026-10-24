/**
 * frontend/src/lib/format.ts
 * Shared display formatters. Money is stored and sent from the backend in
 * CENTS everywhere — divide by 100 exactly once, here, at the display edge.
 */

export function formatKES(cents: number | null | undefined): string {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

/** Compact money for tight spaces: KES 12.4k / KES 1.2M. */
export function formatKESCompact(cents: number | null | undefined): string {
    if (!cents) return "KES 0";
    const kes = cents / 100;
    if (kes >= 1_000_000) return `KES ${(kes / 1_000_000).toFixed(1)}M`;
    if (kes >= 1_000) return `KES ${(kes / 1_000).toFixed(1)}k`;
    return `KES ${Math.round(kes).toLocaleString("en-KE")}`;
}


/** ── Restaurant OS additions ────────────────────────────────────────────── */

const kes = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", maximumFractionDigits: 0 });

/** KES from a WHOLE-KES value (overview/reports feed). Distinct from formatKES(cents). */
export const fmtKes = (n: number) => kes.format(n || 0);
export const fmtPct = (n: number) => `${(n || 0).toFixed(1)}%`;

export function greetingFor(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}
export const greetingNow = () => greetingFor(Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Africa/Nairobi", hour: "2-digit", hourCycle: "h23" }).format(new Date())));

export const fmtDate = () =>
  new Date().toLocaleDateString("en-KE", { timeZone: "Africa/Nairobi", weekday: "long", day: "numeric", month: "long" });

/** A clock the owner can trust: Nairobi, not the browser's zone. */
export function nairobiClock(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-KE", {
    timeZone: "Africa/Nairobi", hour: "numeric", minute: "2-digit", hour12: true,
  }).format(now).replace(/\s?(am|pm)/i, (m) => ` ${m.trim().toLowerCase()}`);
}
