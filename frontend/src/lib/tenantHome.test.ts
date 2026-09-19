/**
 * Where a signed-in user lands.
 *
 * This is the function that dropped a Vibanda waiter on a dead page. homeFor()
 * looked only at the tenant name, so any Vibanda user went to /vibanda — an
 * OWNER surface where GET /overview/today is ADMIN-only. Every call returned
 * 403 and the page showed a generic error with no route out. The layout guards
 * made it worse by pointing at each other: app/staff/layout.tsx sent staff to
 * /dashboard and app/dashboard/layout.tsx sent Vibanda users back to /vibanda.
 *
 * Three lines of logic, a production dead end, and no test. That is the reason
 * this file (and the runner under it) exists.
 */
import { describe, it, expect } from "vitest";
import { homeForUser, homeFor, isVibanda, VIBANDA_TENANT } from "@/lib/tenantHome";

describe("isVibanda", () => {
  it("matches the tenant name regardless of case or padding", () => {
    expect(isVibanda("Vibanda Village")).toBe(true);
    expect(isVibanda("vibanda village")).toBe(true);
    expect(isVibanda("  Vibanda Village  ")).toBe(true);
  });

  it("does not match anything else", () => {
    expect(isVibanda("Vibanda Village Ltd")).toBe(false);
    expect(isVibanda("Chakula House")).toBe(false);
    expect(isVibanda(null)).toBe(false);
    expect(isVibanda(undefined)).toBe(false);
    expect(isVibanda("")).toBe(false);
  });

  it("is a single literal, so renaming the tenant moves every user", () => {
    // Not a bug so much as a fact worth pinning: the whole product fork is one
    // string comparison. Renaming the tenant in the database silently sends
    // every user to the generic dashboard at their next login.
    expect(VIBANDA_TENANT).toBe("Vibanda Village");
    expect(isVibanda(`${VIBANDA_TENANT} Ltd`)).toBe(false);
  });
});

describe("homeForUser", () => {
  it("sends the Vibanda owner to their own shell", () => {
    expect(homeForUser({ tenant_name: "Vibanda Village", role: "admin" }))
      .toBe("/vibanda");
  });

  it("sends every other owner to the generic dashboard", () => {
    expect(homeForUser({ tenant_name: "Chakula House", role: "admin" }))
      .toBe("/dashboard");
  });

  it("sends a Vibanda waiter to their OWN pages, not the owner's", () => {
    // The bug. /vibanda 403s for them on every call.
    expect(homeForUser({
      tenant_name: "Vibanda Village", role: "staff", staff_role: "waiter",
    })).toBe("/staff/waiter");
  });

  it.each([
    ["manager", "/staff/manager"],
    ["supervisor", "/staff/supervisor"],
    ["controller", "/staff/controller"],
    ["stockkeeper", "/staff/stockkeeper"],
    ["kitchen", "/staff/kitchen"],
    ["waiter", "/staff/waiter"],
  ])("routes a Vibanda %s to %s", (tier, expected) => {
    expect(homeForUser({
      tenant_name: "Vibanda Village", role: "staff", staff_role: tier,
    })).toBe(expected);
  });

  it("routes a staff member by role whatever the tenant", () => {
    expect(homeForUser({
      tenant_name: "Chakula House", role: "staff", staff_role: "kitchen",
    })).toBe("/staff/kitchen");
  });

  it("sends a staff account with no tier somewhere that explains itself", () => {
    // /dashboard renders "ask your manager to assign your role" rather than a
    // page of 403s.
    expect(homeForUser({
      tenant_name: "Vibanda Village", role: "staff", staff_role: null,
    })).toBe("/dashboard");
  });

  it("treats an owner whose staff_role happens to be set as an owner", () => {
    // Role.ADMIN is the authority; staff_role is a second, finer axis. An
    // owner row carrying staff_role "owner" must not be routed as staff.
    expect(homeForUser({
      tenant_name: "Vibanda Village", role: "admin", staff_role: "owner",
    })).toBe("/vibanda");
  });

  it("is case-insensitive about the role", () => {
    expect(homeForUser({
      tenant_name: "Vibanda Village", role: "STAFF", staff_role: "waiter",
    })).toBe("/staff/waiter");
  });

  it("does not throw on a missing or empty user", () => {
    expect(homeForUser(null)).toBe("/dashboard");
    expect(homeForUser(undefined)).toBe("/dashboard");
    expect(homeForUser({})).toBe("/dashboard");
  });
});

describe("homeFor (deprecated)", () => {
  it("still answers correctly for an owner", () => {
    expect(homeFor("Vibanda Village")).toBe("/vibanda");
    expect(homeFor("Chakula House")).toBe("/dashboard");
  });

  it("cannot tell an owner from a waiter — which is why it is deprecated", () => {
    // Kept so any remaining caller compiles. This assertion documents the
    // limitation rather than endorsing it: a tenant name carries no role.
    expect(homeFor("Vibanda Village")).toBe("/vibanda");
  });
});
