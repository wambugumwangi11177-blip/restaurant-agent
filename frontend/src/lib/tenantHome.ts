/** Vibanda Village gets a dedicated 3-page experience; every other tenant
 * keeps the full generic dashboard. Single source of truth for that fork. */
export const VIBANDA_TENANT = "Vibanda Village";
export const VIBANDA_SYNTHETIC_TENANT = "Vibanda Village — Synthetic";
export function isVibanda(tenantName?: string | null): boolean {
  const normalized = (tenantName ?? "").trim().toLowerCase();
  return normalized === VIBANDA_TENANT.toLowerCase()
    || (process.env.NEXT_PUBLIC_SYNTHETIC_DEMO === "true" && normalized === VIBANDA_SYNTHETIC_TENANT.toLowerCase());
}
/** Demo Restaurant: a clone of the Vibanda shell under /demo that records its
 * data directly — it never waits on MacSoft or any external data push. */
export const DEMO_TENANT = "Demo Restaurant";
export function isDemoRestaurant(tenantName?: string | null): boolean {
  return (tenantName ?? "").trim().toLowerCase() === DEMO_TENANT.toLowerCase();
}
export function homeFor(tenantName?: string | null): string {
  if (isDemoRestaurant(tenantName)) return "/demo";
  return isVibanda(tenantName) ? "/vibanda" : "/dashboard";
}
