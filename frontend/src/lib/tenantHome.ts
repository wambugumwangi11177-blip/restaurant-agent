import { tierHome, type StaffTier } from "@/lib/permissions";

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
/** Where the owner of every tenant lands: one shell (Home · OS · Reports), configured per tenant in tenantConfig.ts. */
export const OWNER_HOME = "/home";

type Account = { role?: string | null; staff_role?: string | null; tenant_name?: string | null } | null | undefined;

/** An owner is an ADMIN (or SUPERADMIN) system account; any role "staff" belongs on its own tier's screens. */
export function isOwnerAccount(user: Account): boolean {
  const role = (user?.role ?? "").toLowerCase();
  return role === "admin" || role === "superadmin";
}

/** Owners of every tenant land in the OwnerShell; everyone else on their own tier's home (/dashboard for managers). */
export function homeFor(user: Account): string {
  if (!user) return "/dashboard";              // not resolved yet: the dashboard sends a signed-out visitor to /login
  return isOwnerAccount(user) ? OWNER_HOME : tierHome((user.staff_role ?? null) as StaffTier | null);
}
