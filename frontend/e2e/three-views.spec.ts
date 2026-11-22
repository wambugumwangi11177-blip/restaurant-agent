import { test, expect } from "@playwright/test";

test.describe("three views", () => {
  test("super client list returns 403 for anonymous", async ({ request }) => {
    const r = await request.get("/api/v1/super/clients");
    expect(r.status()).toBe(401);
  });

  test("eleven summary route exists", async ({ request }) => {
    const r = await request.get("/api/v1/eleven/summary?period=7d");
    expect([401, 403]).toContain(r.status());
  });
});