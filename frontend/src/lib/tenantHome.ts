/** Eleven — owner shell aligned with mockups/owner (5-tab glass UI). */
export const ELEVEN_TENANT = "Eleven";
export function isEleven(tenantName?: string | null): boolean {
  return (tenantName ?? "").trim().toLowerCase() === ELEVEN_TENANT.toLowerCase();
}
/** Demo Restaurant uses the same direct-entry stack as Eleven (backend demo API unchanged). */
export const DEMO_TENANT = "Demo Restaurant";
export function isDemoRestaurant(tenantName?: string | null): boolean {
  return (tenantName ?? "").trim().toLowerCase() === DEMO_TENANT.toLowerCase();
}
export function homeFor(tenantName?: string | null, staffRole?: string | null): string {
  const role = (staffRole ?? "").trim().toLowerCase();
  if (role === "stockkeeper" || role === "controller") return "/store";
  return "/eleven";
}