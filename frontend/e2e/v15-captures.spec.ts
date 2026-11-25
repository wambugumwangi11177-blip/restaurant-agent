import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const STORE_OUT = "/cursor/stores/self/artifacts";

const PAGES = [
  { slug: "home", path: "/eleven", ready: /tickets|Needs you|Waiting on/i },
  { slug: "money-bills", path: "/eleven/money/bills", ready: /Bills due|Cash after|due ·/i },
  { slug: "stock", path: "/eleven/stock", ready: /days left|Stock levels/i },
] as const;

async function login(page, email: string) {
  const pass = process.env.OWNER_PASSWORD || "";
  if (!pass) test.skip();
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(pass);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 60000 });
  const pin = process.env.SEED_OWNER_PIN || "2468";
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app";
  const loginResp = await page.request.post(`${apiBase}/api/v1/auth/login`, {
    data: { email, password: pass },
  });
  const loginJson = await loginResp.json().catch(() => ({}));
  if (loginJson.access_token) {
    await page.request.post(`${apiBase}/api/v1/auth/pin/unlock`, {
      headers: { Authorization: `Bearer ${loginJson.access_token}` },
      data: { pin },
    });
  }
  await page.evaluate(() => {
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
}

async function unlockPin(page) {
  const pin = process.env.SEED_OWNER_PIN || "2468";
  const lock = page.getByText(/Enter your 4-digit PIN/i);
  if (!(await lock.isVisible().catch(() => false))) return;
  const pad = page.getByLabel("PIN keypad");
  for (const digit of pin.split("")) {
    await pad.getByRole("button", { name: digit, exact: true }).click();
    await page.waitForTimeout(80);
  }
  await expect(lock).toBeHidden({ timeout: 30000 });
}

test("v15 targeted captures", async ({ browser }) => {
  test.setTimeout(400_000);
  fs.mkdirSync(STORE_OUT, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
  const page = await ctx.newPage();
  await login(page, "owner@eleven.leviii");
  for (const p of PAGES) {
    await page.goto(p.path, { waitUntil: "networkidle", timeout: 90000 });
    await unlockPin(page);
    await expect(page.getByText(p.ready).first()).toBeVisible({ timeout: 45000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(STORE_OUT, `v15-data-${p.slug}.png`), fullPage: false });
  }
  await page.goto("/eleven/ask", { waitUntil: "networkidle" });
  await unlockPin(page);
  await page.getByRole("button", { name: /How are sales today/i }).click();
  await expect(page.getByText(/KES|sold/i).first()).toBeVisible({ timeout: 60000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(STORE_OUT, "v15-data-ask-numeric.png"), fullPage: false });

  await page.goto("/eleven", { waitUntil: "networkidle" });
  await unlockPin(page);
  const restock = page.locator('a[href*="/eleven/decisions/restock"]').first();
  await expect(restock).toBeVisible({ timeout: 45000 });
  await restock.click();
  await page.waitForURL(/\/eleven\/decisions\/restock\//, { timeout: 30000 });
  await expect(page.getByText(/What we saw|Approve|runs out/i).first()).toBeVisible({ timeout: 45000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(STORE_OUT, "v15-data-decision-detail.png"), fullPage: false });

  await ctx.close();
});