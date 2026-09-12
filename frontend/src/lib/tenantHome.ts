/** Vibanda Village gets a dedicated 3-page experience; every other tenant
 * keeps the full generic dashboard. Single source of truth for that fork. */
export const VIBANDA_TENANT = "Vibanda Village";
export function isVibanda(tenantName?: string | null): boolean {
  return (tenantName ?? "").trim().toLowerCase() === VIBANDA_TENANT.toLowerCase();
}
export function homeFor(tenantName?: string | null): string {
  return isVibanda(tenantName) ? "/vibanda" : "/dashboard";
}