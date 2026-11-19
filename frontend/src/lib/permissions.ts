/** Post-login routing for staff tiers (Eleven owner shell vs store). */

export type StaffTier =
    | "owner"
    | "manager"
    | "supervisor"
    | "controller"
    | "stockkeeper"
    | "kitchen"
    | "waiter";

export function tierHome(tier: StaffTier | null): string {
    if (!tier || tier === "owner") return "/eleven";
    if (tier === "stockkeeper" || tier === "controller") return "/store";
    return "/store";
}