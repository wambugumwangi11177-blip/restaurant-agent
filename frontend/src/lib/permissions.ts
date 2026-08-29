/**
 * Single source of truth for UI-level role access — directive 015's
 * permission matrix (directives/015_staff_roles_permissions.md).
 *
 * UI-ONLY. The backend's `require_staff_role()` gates (see each router's
 * `_CAN_*` tuples) are the actual authority — this file must be kept in sync
 * with them and with the matrix, or the UI will show something the API then
 * rejects. It replaced the old hand-maintained `access` arrays in
 * `dashboard/layout.tsx`, which had drifted (the "manager" tier was missing
 * from most of them) — a single module beats N per-route arrays.
 */

export type StaffTier =
    | "owner"
    | "manager"
    | "supervisor"
    | "controller"
    | "stockkeeper"
    | "kitchen"
    | "waiter";

export type Access = "rw" | "r" | "none";

export type Domain =
    | "pos"
    | "orders"
    | "kitchen"
    | "inventory"
    | "menu"
    | "reservations"
    | "sales"
    | "roi"
    | "ai"
    | "aiOps"
    | "marketing"
    | "staff"
    | "purchasing"
    | "support";

// Owner is intentionally absent from every row: an Owner account is
// Role.ADMIN, not a "staff" account, and always has full RW access — it
// never consults this matrix (see isStaffAccount checks at call sites).
const MATRIX: Record<Domain, Partial<Record<Exclude<StaffTier, "owner">, Access>>> = {
    pos:           { manager: "rw", supervisor: "rw", waiter: "rw" },
    orders:        { manager: "rw", supervisor: "rw", waiter: "rw", controller: "r", kitchen: "r" },
    kitchen:       { manager: "rw", supervisor: "rw", kitchen: "rw", waiter: "r" },
    inventory:     { manager: "rw", stockkeeper: "rw", controller: "r", kitchen: "r" },
    menu:          { manager: "rw", supervisor: "r", kitchen: "r", waiter: "r" },
    reservations:  { manager: "rw", supervisor: "rw", waiter: "rw" },
    sales:         { manager: "rw", supervisor: "r", controller: "r" },
    roi:           { manager: "r", controller: "r" },
    ai:            { manager: "r", controller: "r" },
    aiOps:         { manager: "r", controller: "r" },
    marketing:     { manager: "rw" },
    staff:         { manager: "rw" },
    purchasing:    { manager: "rw", supervisor: "rw", controller: "r", stockkeeper: "rw" },
    support:       { manager: "rw", supervisor: "r", controller: "r", stockkeeper: "r", kitchen: "r", waiter: "r" },
};

/** Access level for a tier on a domain. Owner always gets "rw". */
export function accessFor(domain: Domain, tier: StaffTier | null): Access {
    if (!tier) return "none";
    if (tier === "owner") return "rw";
    return MATRIX[domain][tier] ?? "none";
}

export function canRead(domain: Domain, tier: StaffTier | null): boolean {
    return accessFor(domain, tier) !== "none";
}

export function canWrite(domain: Domain, tier: StaffTier | null): boolean {
    return accessFor(domain, tier) === "rw";
}

/** Every domain this tier can at least read — used to build a tier's nav. */
export function domainsFor(tier: StaffTier | null): Domain[] {
    if (!tier) return [];
    return (Object.keys(MATRIX) as Domain[]).filter((d) => canRead(d, tier));
}

/** Where a staff-tier account should land after login / off a disallowed route. */
export const TIER_HOME: Record<Exclude<StaffTier, "owner">, string> = {
    manager: "/staff/manager",
    supervisor: "/staff/supervisor",
    controller: "/staff/controller",
    stockkeeper: "/staff/stockkeeper",
    kitchen: "/staff/kitchen",
    waiter: "/staff/waiter",
};

export function tierHome(tier: StaffTier | null): string {
    if (!tier || tier === "owner") return "/dashboard";
    return TIER_HOME[tier] ?? "/login";
}
