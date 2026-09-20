/** Vibanda Village gets a dedicated 3-page experience; every other tenant
 * keeps the full generic dashboard. Single source of truth for that fork. */
export const VIBANDA_TENANT = "Vibanda Village";
export const VIBANDA_SYNTHETIC_TENANT = "Vibanda Village — Synthetic";
export function isVibanda(tenantName?: string | null): boolean {
  const normalized = (tenantName ?? "").trim().toLowerCase();
  return normalized === VIBANDA_TENANT.toLowerCase()
    || (process.env.NEXT_PUBLIC_SYNTHETIC_DEMO === "true" && normalized === VIBANDA_SYNTHETIC_TENANT.toLowerCase());
}
export function homeFor(tenantName?: string | null): string {
  return isVibanda(tenantName) ? "/vibanda" : "/dashboard";
}
