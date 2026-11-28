import { test, expect, devices, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const API = process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app";
const FRONT = process.env.LIVE_FRONTEND || "https://frontend-test-production-752b1b7c.up.railway.app";
const STAFF_PASS = process.env.SEED_STAFF_PASSWORD || "";
const OWNER_PASS = process.env.SEED_OWNER_PASSWORD || "";
const OUT = process.env.SHOT_DIR || "/workspace/owner-team-activity-shots";

async function token(request: APIRequestContext, email: string, password: string): Promise<string> {
  const res = await request.post(`${API}/api/v1/auth/login`, { data: { email, password } });
  expect(res.ok(), `login ${email}`).toBeTruthy();
  return (await res.json()).access_token;
}

async function session(browser: Browser, tok: string, size: { width: number; height: number }): Promise<Page> {
  const context = await browser.newContext({ ...devices["Pixel 5"], viewport: size, baseURL: FRONT });
  await context.addInitScript((t) => {
    window.sessionStorage.setItem("access_token", t);
    window.sessionStorage.setItem("app_pin_unlocked", "1");
    window.sessionStorage.setItem("app_last_activity", String(Date.now()));
  }, tok);
  return context.newPage();
}

test.skip(!STAFF_PASS || !OWNER_PASS, "SEED_STAFF_PASSWORD and SEED_OWNER_PASSWORD required");

test("a failed request on a staff screen reaches the owner's Team activity", async ({ browser, request }) => {
  const jack = await token(request, "jack@eleven.leviii", STAFF_PASS);
  const owner = await token(request, "owner@eleven.leviii", OWNER_PASS);
  const marker = `Test failure ${Date.now()}`;

  const staff = await session(browser, jack, { width: 360, height: 740 });
  await staff.route("**/api/v1/store/items**", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: marker }) }));
  await staff.goto("/store/stock", { waitUntil: "domcontentloaded" });

  await expect
    .poll(
      async () => {
        const res = await request.get(`${API}/api/v1/eleven/team-activity`, { headers: { Authorization: `Bearer ${owner}` } });
        return (await res.json()).problems.some((p: { message: string; person_name: string }) => p.message.includes(marker) && p.person_name === "Jack");
      },
      { timeout: 45_000 },
    )
    .toBe(true);

  fs.mkdirSync(OUT, { recursive: true });
  for (const [name, size] of [["mobile", { width: 360, height: 740 }], ["desktop", { width: 1280, height: 860 }]] as const) {
    const page = await session(browser, owner, size);
    await page.goto("/eleven/team-activity", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Problems" })).toBeVisible({ timeout: 45_000 });
    await expect(page.locator("main")).toContainText(marker);
    await expect(page.locator("main")).toContainText("EAT");
    await expect(page.locator("main img").first()).toBeVisible({ timeout: 45_000 });
    expect(await page.locator("main").innerText()).not.toMatch(/\bAI\b/);
    await page.screenshot({ path: path.join(OUT, `owner-team-activity-${name}.png`), fullPage: true, animations: "disabled" });
    if (name === "mobile") {
      const amina = await page.locator("select option", { hasText: /^Amina/ }).first().getAttribute("value");
      await page.getByLabel("Person").selectOption(amina!);
      await expect(page.locator("main section li strong", { hasText: /^Amina/ }).first()).toBeVisible();
      await expect(page.locator("main section li strong", { hasText: /^Jack/ })).toHaveCount(0);
      await page.screenshot({ path: path.join(OUT, "owner-team-activity-filtered.png"), fullPage: true, animations: "disabled" });
    }
  }
});
