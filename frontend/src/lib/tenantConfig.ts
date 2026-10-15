/**
 * What differs between restaurants in the OwnerShell, in one place (docs/v2/SPEC.md §2 principle 5: "one OwnerShell driven by
 * tenant config — name, source type, branding"). Nothing else in the shell asks which tenant it is.
 *
 *   source  "macsoft"  the figures are a mirror of the restaurant's point of sale: they are shown only once the delivery is
 *                      reconciled (Home says what it is waiting for until then);
 *           "direct"   the restaurant records its sales and costs here: nothing to wait for.
 */
import { isDemoRestaurant, isVibanda, VIBANDA_SYNTHETIC_TENANT } from "./tenantHome";

export type TenantKind = "vibanda" | "demo" | "standard";
export type SourceKind = "macsoft" | "direct";

export type TenantConfig = {
  kind: TenantKind;
  source: SourceKind;
  /** A standing sentence under the date, or null. */
  banner: string | null;
  /** Show a way to the operational screens (menu, stock, orders …) that live in /dashboard. */
  operations: boolean;
};

const DEMO_BANNER =
  "Demo Restaurant · a made-up restaurant. Every figure is worked out from generated sales and costs, not from a real business.";
const SYNTHETIC_BANNER = "Synthetic staging data · not Macsoft";

export function tenantConfig(tenantName?: string | null): TenantConfig {
  if (isVibanda(tenantName)) {
    const synthetic = (tenantName ?? "").trim().toLowerCase() === VIBANDA_SYNTHETIC_TENANT.toLowerCase();
    return { kind: "vibanda", source: "macsoft", banner: synthetic ? SYNTHETIC_BANNER : null, operations: false };
  }
  if (isDemoRestaurant(tenantName)) return { kind: "demo", source: "direct", banner: DEMO_BANNER, operations: false };
  return { kind: "standard", source: "direct", banner: null, operations: true };
}
