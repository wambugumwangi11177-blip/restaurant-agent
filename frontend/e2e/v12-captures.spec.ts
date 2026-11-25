import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const OUT = process.env.CURSOR_ARTIFACTS || "/opt/cursor/artifacts";
const STORE_OUT = "/cursor/stores/self/artifacts";

const ALL_PAGES = [
  { slug: "home", path: "/eleven", ready: /Needs you|Today|Restock|Nothing needs/i },
  { slug: "money-dishes", path: "/eleven/money/dishes", ready: /Dishes|Menu map|Plate profit|Best sellers|Pilau/i },
  { slug: "stock", path: "/eleven/stock", ready: /Stock levels|Rice|Reorder/i },
  { slug: "stock-suppliers", path: "/eleven/stock/suppliers", ready: /Suppliers|Fresh Farm|price jump/i },
  { slug: "stock-prep", path: "/eleven/stock/prep", ready: /Prep|plates|Pilau/i },
  { slug: "ask", path: "/eleven/ask", ready: /Ask|question/i },
] as const;

const slugFilter = process.env.V12_CAPTURE_SLUGS?.split(",").map((s) => s.trim()).filter(Boolean);
const PAGES = slugFilter?.length ? ALL_PAGES.filter((p) => slugFilter.includes(p.slug)) : ALL_PAGES;

async function login(page) {
  const pass = process.env.OWNER_PASSWORD || "";
  if (!pass) test.skip();
  let accessToken = "";
  await page.route("**/api/v1/auth/login", async (route) => {
    const resp = await route.fetch();
    const json = await resp.json().catch(() => ({}));
    if (json.access_token) accessToken = json.access_token;
    await route.fulfill({ response: resp });
  });
  await page.goto("/login", { waitUntil: "networkidle" });
  await expect(page.getByText(/Checking sign-in/i)).toHaveCount(0, { timeout: 90000 });
  await page.locator('input[type="email"]').waitFor({ state: "visible", timeout: 60000 });
  await page.locator('input[type="email"]').fill("owner@eleven.leviii");
  await page.locator('input[type="password"]').fill(pass);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 60000 });
  const pin = process.env.SEED_OWNER_PIN || "2468";
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app";
  const token = accessToken;
  if (!token) {
    const loginResp = await page.request.post(`${apiBase}/api/v1/auth/login`, {
      data: { email: "owner@eleven.leviii", password: pass },
    });
    const loginJson = await loginResp.json().catch(() => ({}));
    if (loginJson.access_token) {
      await page.request.post(`${apiBase}/api/v1/auth/pin/unlock`, {
        headers: { Authorization: `Bearer ${loginJson.access_token}` },
        data: { pin },
      });
    }
  } else {
    await page.request.post(`${apiBase}/api/v1/auth/pin/unlock`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { pin },
    });
  }
  await page.evaluate(() => {
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
  await page.goto("/eleven", { waitUntil: "networkidle" });
  await unlockPin(page);
}

async function unlockPin(page) {
  const pin = process.env.SEED_OWNER_PIN || "2468";
  const lock = page.getByText(/Enter your 4-digit PIN/i);
  if (!(await lock.isVisible().catch(() => false))) return;
  const unlockWait = page.waitForResponse(
    (r) => r.url().includes("/auth/pin/unlock") && r.status() === 200,
    { timeout: 30000 },
  );
  const pad = page.getByLabel("PIN keypad");
  for (const digit of pin.split("")) {
    await pad.getByRole("button", { name: digit, exact: true }).click();
    await page.waitForTimeout(120);
  }
  await unlockWait;
  await expect(lock).toBeHidden({ timeout: 30000 });
  await page.evaluate(() => {
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
}

async function assertCaptureReady(page) {
  await expect(page.getByText(/Enter your 4-digit PIN/i)).toHaveCount(0);
  await expect(page.getByText(/Loading today/i)).toHaveCount(0);
  await expect(page.getByText(/\d+ Issues?/i)).toHaveCount(0);
  await expect(page.getByText(/Grounded in your records/i)).toHaveCount(0);
  await expect(page.getByText(/Starts when dishes sell on the till/i)).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: /Main/i })).toBeVisible();
}

test("v12 data-stack captures", async ({ browser }) => {
  test.setTimeout(300_000);
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(STORE_OUT, { recursive: true });
  const shots: string[] = [];
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
  const page = await ctx.newPage();
  page.on("dialog", (d) => d.dismiss());
  await login(page);
  for (const p of PAGES) {
    await page.goto(p.path, { waitUntil: "networkidle", timeout: 90000 });
    await unlockPin(page);
    await expect(page.getByText(p.ready).first()).toBeVisible({ timeout: 45000 });
    await page.waitForTimeout(2500);
    await assertCaptureReady(page);
    const file = path.join(OUT, `v12-data-${p.slug}.png`);
    const storeFile = path.join(STORE_OUT, `v12-data-${p.slug}.png`);
    await page.screenshot({ path: file, fullPage: false });
    fs.copyFileSync(file, storeFile);
    shots.push(storeFile);
  }
  await ctx.close();
  fs.writeFileSync(path.join(STORE_OUT, "v12-capture-list.json"), JSON.stringify(shots, null, 2));
});