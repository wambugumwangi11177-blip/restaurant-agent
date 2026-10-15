import { expect, it } from "vitest";
import { homeFor, isOwnerAccount, OWNER_HOME } from "@/lib/tenantHome";
import { tenantConfig } from "@/lib/tenantConfig";

it("owners of every tenant land in the one owner shell; everyone else on their own tier's home", () => {
  for (const tenant_name of ["Vibanda Village", "Demo Restaurant", "Mama Oliech", null]) {
    expect(homeFor({ role: "admin", staff_role: "owner", tenant_name })).toBe(OWNER_HOME);
    expect(homeFor({ role: "superadmin", staff_role: null, tenant_name })).toBe(OWNER_HOME);
  }
  expect(homeFor({ role: "staff", staff_role: "manager", tenant_name: "Mama Oliech" })).toBe("/staff/manager");
  expect(homeFor({ role: "staff", staff_role: "waiter", tenant_name: "Vibanda Village" })).toBe("/staff/waiter");
  expect(homeFor(null)).toBe("/dashboard");                      // not resolved yet: the dashboard sends a signed-out visitor to /login
});

it("only an ADMIN or SUPERADMIN account is an owner, whatever the case it is spelled in", () => {
  expect(isOwnerAccount({ role: "ADMIN" })).toBe(true);
  expect(isOwnerAccount({ role: "staff", staff_role: "owner" })).toBe(false);
  expect(isOwnerAccount(null)).toBe(false);
});

it("the tenant config says where a restaurant's figures come from and what its shell shows", () => {
  expect(tenantConfig("Vibanda Village")).toMatchObject({ kind: "vibanda", source: "macsoft", operations: false });
  expect(tenantConfig("vibanda village").source).toBe("macsoft");
  expect(tenantConfig(" Demo Restaurant ")).toMatchObject({ kind: "demo", source: "direct", operations: false });
  expect(tenantConfig("Demo Restaurant").banner).toMatch(/made-up restaurant/);
  expect(tenantConfig("Mama Oliech")).toEqual({ kind: "standard", source: "direct", banner: null, operations: true });
  expect(tenantConfig(undefined).kind).toBe("standard");
});
