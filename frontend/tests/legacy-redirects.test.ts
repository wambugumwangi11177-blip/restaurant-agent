import { expect, it } from "vitest";
import nextConfig from "../next.config";
import { LEGACY_AREA } from "@/lib/owner/blocks";
import { AREA_KEYS } from "@/lib/owner/types";

const VIBANDA_SLUGS = ["revenue", "orders", "kitchen", "stock", "bookings", "team", "menu", "finance", "expenses", "suppliers", "purchasing", "cash-reconciliation", "pos", "marketing", "risk", "notifications", "intelligence", "data-trust", "audit", "settings"];

async function redirects() {
  const list = await nextConfig.redirects!();
  return new Map(list.map((r) => [r.source, r.destination]));
}

it("the old owner addresses all land on the new shell, for both old shells", async () => {
  const map = await redirects();
  for (const shell of ["vibanda", "demo"]) {
    expect(map.get(`/${shell}`)).toBe("/home");
    expect(map.get(`/${shell}/os`)).toBe("/os");
    expect(map.get(`/${shell}/reports`)).toBe("/reports");
    expect(map.get(`/${shell}/stock`)).toBe("/home#area-store");
    expect(map.get(`/${shell}/cash-reconciliation`)).toBe("/home#area-cash");
    expect(map.get(`/${shell}/anything/else`) ?? map.get(`/${shell}/:other*`)).toBe("/home");
  }
});

it("every page of the old Vibanda shell has a home on a panel, and every panel it points at exists", () => {
  const slugs = VIBANDA_SLUGS;
  expect(slugs.filter((slug) => !(slug in LEGACY_AREA))).toEqual([]);
  for (const area of Object.values(LEGACY_AREA)) expect(AREA_KEYS).toContain(area);
});

it("a redirect never shadows a page that still exists", async () => {
  const sources = [...(await redirects()).keys()];
  for (const live of ["/home", "/os", "/reports", "/dashboard", "/login", "/order", "/staff"]) expect(sources).not.toContain(live);
});
