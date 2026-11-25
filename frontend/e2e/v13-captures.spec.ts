import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const OUT = process.env.CURSOR_ARTIFACTS || "/opt/cursor/artifacts";
const STORE_OUT = "/cursor/stores/self/artifacts";

const STACKS = [
  { state: "data", email: "owner@eleven.leviii" },
  { state: "empty", email: "owner-empty@eleven.leviii" },
] as const;

const DATA_PAGES = [
  { slug: "home", path: "/eleven", ready: /Needs you|Today|Nothing needs/i },
  { slug: "money", path: "/eleven/money", ready: /Sales ·|What this shows/i },
  { slug: "money-pnl", path: "/eleven/money/pnl", ready: /You kept|What this shows|Monthly|P&L|Starts when/i },
  { slug: "money-dishes", path: "/eleven/money/dishes", ready: /Menu map|sells well|What this shows/i },
  { slug: "money-bills", path: "/eleven/money/bills", ready: /Bills|Cash after|What this shows/i },
  { slug: "stock", path: "/eleven/stock", ready: /Stock levels|What this shows/i },
  { slug: "stock-suppliers", path: "/eleven/stock/suppliers", ready: /Supplier|What this shows/i },
  { slug: "stock-prep", path: "/eleven/stock/prep", ready: /prep|plates|What this shows/i },
  { slug: "more-team", path: "/eleven/more/team", ready: /On shift|Team|Jack|What this shows/i },
  { slug: "settings-reports", path: "/eleven/settings/reports", ready: /Report|reports/i },
] as const;

const EMPTY_ONLY = [
  { slug: "home", path: "/eleven", ready: /Get started|Nothing needs/i },
  { slug: "money", path: "/eleven/money", ready: /Money|Starts when/i },
] as const;

const slugFilter = process.env.V13_CAPTURE_SLUGS?.split(",").map((s) => s.trim()).filter(Boolean);
const stackFilter = process.env.V13_CAPTURE_STACK?.trim();

async function login(page, email: string) {
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
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(pass);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 60000 });
  const pin = process.env.SEED_OWNER_PIN || "2468";
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app";
  const token = accessToken;
  if (!token) {
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
  await expect(page.getByRole("navigation", { name: /Main/i })).toBeVisible();
}

async function captureAskNumeric(page) {
  await page.goto("/eleven/ask", { waitUntil: "networkidle" });
  await unlockPin(page);
  await page.getByRole("button", { name: /How are sales today/i }).click();
  await expect(page.getByText(/What this shows|Live ·/i).first()).toBeVisible({ timeout: 60000 });
  await page.waitForTimeout(2000);
  const storeFile = path.join(STORE_OUT, "v13-data-ask-numeric.png");
  await page.screenshot({ path: storeFile, fullPage: false });
  return storeFile;
}

test("v13 data-stack captures", async ({ browser }) => {
  test.setTimeout(600_000);
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(STORE_OUT, { recursive: true });
  const pages = slugFilter?.length ? DATA_PAGES.filter((p) => slugFilter.includes(p.slug)) : DATA_PAGES;
  const shots: string[] = [];
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
  const page = await ctx.newPage();
  page.on("dialog", (d) => d.dismiss());
  await login(page, "owner@eleven.leviii");
  for (const p of pages) {
    await page.goto(p.path, { waitUntil: "networkidle", timeout: 90000 });
    await unlockPin(page);
    await expect(page.getByText(p.ready).first()).toBeVisible({ timeout: 45000 });
    await page.waitForTimeout(2500);
    await assertCaptureReady(page);
    const storeFile = path.join(STORE_OUT, `v13-data-${p.slug}.png`);
    await page.screenshot({ path: storeFile, fullPage: false });
    shots.push(storeFile);
  }
  shots.push(await captureAskNumeric(page));
  await page.goto("/eleven", { waitUntil: "networkidle" });
  await unlockPin(page);
  const restock = page.getByText(/Restock|Approve|needs you/i).first();
  if (await restock.isVisible().catch(() => false)) {
    await restock.click();
    await page.waitForTimeout(1500);
    const dec = path.join(STORE_OUT, "v13-data-decision-detail.png");
    await page.screenshot({ path: dec, fullPage: false });
    shots.push(dec);
  }
  await page.close();
  if (!stackFilter || stackFilter === "empty") {
    const emptyPage = await ctx.newPage();
    await login(emptyPage, "owner-empty@eleven.leviii");
    for (const p of EMPTY_ONLY) {
      await emptyPage.goto(p.path, { waitUntil: "networkidle", timeout: 90000 });
      await unlockPin(emptyPage);
      await emptyPage.waitForTimeout(2000);
      const storeFile = path.join(STORE_OUT, `v13-empty-${p.slug}.png`);
      await emptyPage.screenshot({ path: storeFile, fullPage: false });
      shots.push(storeFile);
    }
    await emptyPage.close();
  }
  await ctx.close();
  fs.writeFileSync(path.join(STORE_OUT, "v13-capture-list.json"), JSON.stringify(shots, null, 2));
});