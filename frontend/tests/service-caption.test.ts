import { expect, it } from "vitest";
import { serviceCaption } from "@/lib/owner/format";

it("names the trading day, and says the service is still open before 06:00", () => {
  expect(serviceCaption(new Date("2026-10-23T22:30:00Z"))).toBe("Fri 23 Oct service, still open");
  expect(serviceCaption(new Date("2026-10-24T11:00:00Z"))).toBe("Sat 24 Oct service");
});
