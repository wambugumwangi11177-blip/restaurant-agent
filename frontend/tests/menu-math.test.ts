import { expect, it } from "vitest";
import { monthGainCents, targetPriceCents } from "@/lib/menuMath";

it("a price is the next step that keeps the share, and a month's change is the gap times the plates", () => {
  expect(targetPriceCents(26000, 45, 100)).toBe(47300);
  expect(monthGainCents(40000, 43500, 300)).toBe(1_050_000);
});
