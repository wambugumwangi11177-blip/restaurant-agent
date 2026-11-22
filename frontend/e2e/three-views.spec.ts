import { test, expect } from "@playwright/test";

test.describe("three views", () => {
  test("platform API is not public", async ({ request }) => {
    const r = await request.get("/api/v1/admin/platform/restaurants");
    expect(r.status()).toBe(401);
  });

  test("legacy super UI route is gone", async ({ page }) => {
    const res = await page.goto("/super");
    expect(res?.status()).toBe(404);
  });

  test("eleven summary requires auth", async ({ request }) => {
    const r = await request.get("/api/v1/eleven/summary?period=7d");
    expect([401, 403]).toContain(r.status());
  });
});