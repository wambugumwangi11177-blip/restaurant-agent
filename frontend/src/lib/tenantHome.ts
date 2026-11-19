/** Vibanda Village — dedicated demo shell under /vibanda (internal QA only). */
export const VIBANDA_TENANT = "Vibanda Village";
export const VIBANDA_SYNTHETIC_TENANT = "Vibanda Village — Synthetic";
export function isVibanda(tenantName?: string | null): boolean {
  const normalized = (tenantName ?? "").trim().toLowerCase();
  return normalized === VIBANDA_TENANT.toLowerCase()
    || (process.env.NEXT_PUBLIC_SYNTHETIC_DEMO === "true" && normalized === VIBANDA_SYNTHETIC_TENANT.toLowerCase());
}
/** Demo Restaurant tenants reuse the Vibanda shell (backend demo API unchanged). */
export const DEMO_TENANT = "Demo Restaurant";
export function isDemoRestaurant(tenantName?: string | null): boolean {
  return (tenantName ?? "").trim().toLowerCase() === DEMO_TENANT.toLowerCase();
}
/** Eleven — owner shell aligned with mockups/owner (5-tab glass UI). */
export const ELEVEN_TENANT = "Eleven";
export function isEleven(tenantName?: string | null): boolean {
  return (tenantName ?? "").trim().toLowerCase() === ELEVEN_TENANT.toLowerCase();
}
export function homeFor(tenantName?: string | null, staffRole?: string | null): string {
  const role = (staffRole ?? "").trim().toLowerCase();
  if (role === "stockkeeper" || role === "controller") return "/store";
  if (isDemoRestaurant(tenantName)) return "/vibanda";
  if (isEleven(tenantName)) return "/eleven";
  if (isVibanda(tenantName)) return "/vibanda";
  return "/eleven";
}
