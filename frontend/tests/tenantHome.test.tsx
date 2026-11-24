import { describe, expect, it } from "vitest";
import { homeFor } from "@/lib/tenantHome";

const ROLES = ["owner", "manager", "stockkeeper", "controller", "supervisor", "kitchen", "waiter", ""] as const;

describe("homeFor", () => {
  it.each([
    ["owner", "/eleven"],
    ["", "/eleven"],
    ["manager", "/store"],
    ["stockkeeper", "/store"],
    ["controller", "/store"],
    ["supervisor", "/store"],
    ["kitchen", "/store"],
    ["waiter", "/store"],
  ] as const)("routes %s to %s", (role, expected) => {
    expect(homeFor("Eleven", role)).toBe(expected);
  });

  it("covers every staff tier without sending floor managers to /eleven", () => {
    for (const role of ROLES) {
      const dest = homeFor("Eleven", role);
      expect(dest).toMatch(/^\/(eleven|store)$/);
      if (role === "manager" || role === "stockkeeper" || role === "controller") {
        expect(dest).toBe("/store");
      }
      if (role === "owner" || role === "") {
        expect(dest).toBe("/eleven");
      }
    }
  });
});