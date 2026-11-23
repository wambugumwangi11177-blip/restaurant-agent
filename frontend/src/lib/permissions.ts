/** Post-login routing for staff tiers (Eleven owner shell vs store). */

export type StaffTier =
    | "owner"
    | "manager"
    | "supervisor"
    | "controller"
    | "stockkeeper"
    | "kitchen"
    | "waiter";

import { homeFor } from "@/lib/tenantHome";

/** @deprecated Use homeFor — single post-login router. */
export function tierHome(tier: StaffTier | null): string {
    return homeFor(null, tier);
}