import { describe, expect, it } from "vitest";
import { isVerifiedVibandaSource } from "@/lib/vibandaSource";

describe("Vibanda source trust gate", () => {
  it("keeps the owner view waiting before the first delivery", () => {
    expect(isVerifiedVibandaSource({ state: "awaiting_first_delivery", reconciled: false })).toBe(false);
  });

  it("keeps metrics hidden when records arrived but are not reconciled", () => {
    expect(isVerifiedVibandaSource({ state: "receiving", reconciled: false })).toBe(false);
  });

  it("allows live metrics only for receiving and reconciled data", () => {
    expect(isVerifiedVibandaSource({ state: "receiving", reconciled: true })).toBe(true);
  });

  it("does not treat an unreadable source as verified", () => {
    expect(isVerifiedVibandaSource({ state: "unavailable", reconciled: true })).toBe(false);
    expect(isVerifiedVibandaSource(null)).toBe(false);
  });
});
