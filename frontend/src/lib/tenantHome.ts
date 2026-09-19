/** Where a signed-in user belongs. Single source of truth for that fork.
 *
 * Vibanda Village gets a dedicated 3-page experience; every other tenant keeps
 * the full generic dashboard. But the fork is not tenant alone: `/vibanda` is
 * an OWNER surface — GET /overview/today is gated to ADMIN (backend/auth.py's
 * require_staff_role with an empty allow-set), so a waiter sent there gets a
 * 403 on every call and a generic error screen with no route out.
 *
 * That is exactly what used to happen. homeFor() looked only at the tenant,
 * app/staff/layout.tsx sent staff to /dashboard, and app/dashboard/layout.tsx
 * checked isVibanda BEFORE the staff role and sent them straight back to
 * /vibanda. The two guards pointed at each other and a Vibanda staff member
 * bounced into a dead page. Staff role is checked first here for that reason.
 */
import { tierHome, type StaffTier } from "@/lib/permissions";

export const VIBANDA_TENANT = "Vibanda Village";

export function isVibanda(tenantName?: string | null): boolean {
  return (tenantName ?? "").trim().toLowerCase() === VIBANDA_TENANT.toLowerCase();
}

type HomeUser = {
  tenant_name?: string | null;
  role?: string | null;
  staff_role?: string | null;
};

/** The landing route for a user. Pass the whole user — a tenant name alone
 *  cannot tell an owner from a waiter, which was the bug. */
export function homeForUser(user?: HomeUser | null): string {
  const isStaffAccount = (user?.role ?? "").toLowerCase() === "staff";
  const staffRole = (user?.staff_role ?? null) as StaffTier | null;

  // A staff member goes to their own tier home whatever the tenant. Their
  // pages work; the owner's do not, for them.
  if (isStaffAccount && staffRole) return tierHome(staffRole);
  // A staff account with no tier assigned has nowhere working to go. Send them
  // to the generic shell, which renders the "ask your manager to assign your
  // role" state rather than a page of 403s.
  if (isStaffAccount) return "/dashboard";

  return isVibanda(user?.tenant_name) ? "/vibanda" : "/dashboard";
}

/** @deprecated Use homeForUser — a tenant name cannot tell an owner from a
 *  waiter. Kept so any remaining caller keeps compiling, and it still answers
 *  correctly for an owner. */
export function homeFor(tenantName?: string | null): string {
  return isVibanda(tenantName) ? "/vibanda" : "/dashboard";
}
