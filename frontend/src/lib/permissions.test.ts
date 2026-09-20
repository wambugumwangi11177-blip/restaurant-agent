/**
 * The permission matrix — directive 015's table, as the UI reads it.
 *
 * This file's own docstring says it must be kept in sync with the backend's
 * require_staff_role() gates, "or the UI will show something the API then
 * rejects". Nothing enforced that. These tests pin the decisions the directive
 * made deliberately, so a convenient-looking loosening fails here rather than
 * showing a Waiter a link that 403s.
 *
 * UI-only, by design: the backend is the authority. A test here proving a
 * Waiter cannot see the stock nav is not a security claim — it is a claim that
 * we do not dangle a door they cannot open.
 */
import { describe, it, expect } from "vitest";
import {
  accessFor, canRead, canWrite, domainsFor, tierHome,
  type Domain, type StaffTier,
} from "@/lib/permissions";

const TIERS: StaffTier[] = [
  "owner", "manager", "supervisor", "controller", "stockkeeper", "kitchen", "waiter",
];

describe("the owner", () => {
  it("has write access everywhere without consulting the matrix", () => {
    const domains: Domain[] = [
      "pos", "orders", "kitchen", "inventory", "menu", "reservations",
      "sales", "roi", "ai", "aiOps", "marketing", "staff", "purchasing", "support",
    ];
    for (const d of domains) {
      expect(accessFor(d, "owner"), d).toBe("rw");
    }
  });
});

describe("separation of duties", () => {
  it("lets the Controller read inventory but never move stock", () => {
    // The point of the role. The person reconciling a stock variance must not
    // be the person who could cover a shortfall — directive 015 calls this out
    // explicitly and says not to collapse Controller into Manager for
    // convenience.
    expect(canRead("inventory", "controller")).toBe(true);
    expect(canWrite("inventory", "controller")).toBe(false);
  });

  it("keeps the Controller read-only on orders and sales too", () => {
    expect(accessFor("orders", "controller")).toBe("r");
    expect(accessFor("sales", "controller")).toBe("r");
  });

  it("gives the Controller no POS access at all", () => {
    expect(accessFor("pos", "controller")).toBe("none");
  });
});

describe("front-of-house cannot see the money views", () => {
  it.each(["waiter", "kitchen", "stockkeeper"] as StaffTier[])(
    "%s has no access to sales, roi, ai or marketing",
    (tier) => {
      for (const d of ["sales", "roi", "ai", "aiOps", "marketing"] as Domain[]) {
        expect(accessFor(d, tier), `${tier}/${d}`).toBe("none");
      }
    },
  );

  it("a Waiter cannot reach inventory", () => {
    expect(accessFor("inventory", "waiter")).toBe("none");
  });

  it("a Kitchen tier can read inventory but not change it", () => {
    expect(accessFor("inventory", "kitchen")).toBe("r");
  });
});

describe("accessFor", () => {
  it("returns none for a tier with no entry rather than throwing", () => {
    expect(accessFor("marketing", "waiter")).toBe("none");
  });

  it("returns none for an unassigned tier", () => {
    expect(accessFor("orders", null)).toBe("none");
    expect(canRead("orders", null)).toBe(false);
    expect(canWrite("orders", null)).toBe(false);
  });

  it("treats read-write as also readable", () => {
    expect(canRead("pos", "waiter")).toBe(true);
    expect(canWrite("pos", "waiter")).toBe(true);
  });
});

describe("domainsFor", () => {
  it("gives every tier somewhere to go", () => {
    // A tier with an empty nav is a login that lands on nothing — the same
    // class of dead end that sent a Vibanda waiter to a page of 403s.
    for (const tier of TIERS) {
      expect(domainsFor(tier).length, tier).toBeGreaterThan(0);
    }
  });

  it("returns nothing for an unassigned tier", () => {
    expect(domainsFor(null)).toEqual([]);
  });

  it("never lists a domain the tier cannot read", () => {
    for (const tier of TIERS) {
      for (const d of domainsFor(tier)) {
        expect(canRead(d, tier), `${tier}/${d}`).toBe(true);
      }
    }
  });
});

describe("tierHome", () => {
  it("sends each staff tier to its own shell", () => {
    expect(tierHome("manager")).toBe("/staff/manager");
    expect(tierHome("supervisor")).toBe("/staff/supervisor");
    expect(tierHome("controller")).toBe("/staff/controller");
    expect(tierHome("stockkeeper")).toBe("/staff/stockkeeper");
    expect(tierHome("kitchen")).toBe("/staff/kitchen");
    expect(tierHome("waiter")).toBe("/staff/waiter");
  });

  it("sends an owner to the dashboard, not a staff shell", () => {
    expect(tierHome("owner")).toBe("/dashboard");
  });

  it("sends an unassigned tier to the dashboard, which explains itself", () => {
    expect(tierHome(null)).toBe("/dashboard");
  });

  it("gives every tier a home that is a real route", () => {
    for (const tier of TIERS) {
      expect(tierHome(tier), tier).not.toBe("/login");
    }
  });
});
