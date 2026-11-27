/** Eleven — owner glass shell (5-tab UI). */
export const ELEVEN_TENANT = "Eleven";
export function isEleven(tenantName?: string | null): boolean {
  return (tenantName ?? "").trim().toLowerCase() === ELEVEN_TENANT.toLowerCase();
}
export function homeFor(_tenantName?: string | null, staffRole?: string | null): string {
  const role = (staffRole ?? "").trim().toLowerCase();
  if (role === "owner" || role === "") return "/eleven";
  if (role === "manager" || role === "stockkeeper" || role === "controller") return "/store";
  return "/store";
}