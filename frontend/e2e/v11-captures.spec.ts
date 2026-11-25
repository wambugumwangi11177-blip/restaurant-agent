import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const OUT = "/opt/cursor/artifacts";

const STACKS = [
  { state: "data", email: "owner@eleven.leviii" },
  { state: "empty", email: "owner-empty@eleven.leviii" },
] as const;

const PAGES = [
  { slug: "home", path: "/eleven", ready: /Needs you|Get started|Today|Nothing needs/i },
  { slug: "money", path: "/eleven/money", ready: /Money|Today:|Sales —/i },
  { slug: "money-pnl", path: "/eleven/money/pnl", ready: /Full P&L|Monthly P&L|Starts when/i },
  { slug: "money-dishes", path: "/eleven/money/dishes", ready: /Dishes|Menu map/i },
  { slug: "stock", path: "/eleven/stock", ready: /Stock levels|Starts when Jack/i },
  { slug: "stock-suppliers", path: "/eleven/stock/suppliers", ready: /Suppliers|Starts when/i },
  { slug: "stock-prep", path: "/eleven/stock/prep", ready: /Prep|Starts when/i },
  { slug: "more", path: "/eleven/more", ready: /Team|Help|More/i },
  { slug: "settings-reports", path: "/eleven/settings/reports", ready: /Reports|Daily/i },
  { slug: "more-team", path: "/eleven/more/team", ready: /Team|On shift|Jack/i },
  { slug: "money-bills", path: "/eleven/money/bills", ready: /Cash after bills|Bills/i },
  { slug: "settings", path: "/eleven/settings", ready: /Settings|Reports|Targets/i },
  { slug: "ask", path: "/eleven/ask", ready: /Ask|question/i },
] as const;

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
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await expect(page.getByText(/Checking sign-in/i)).toHaveCount(0, { timeout: 90000 });
  await page.locator('input[type="email"]').waitFor({ state: "visible", timeout: 60000 });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(pass);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 60000 });
  const pin = process.env.SEED_OWNER_PIN || "2468";
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  if (accessToken) {
    await page.evaluate(
      async ({ token, pinCode, base }) => {
        await fetch(`${base}/api/v1/auth/pin/unlock`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ pin: pinCode }),
        });
        sessionStorage.setItem("app_pin_unlocked", "1");
        sessionStorage.setItem("app_last_activity", String(Date.now()));
      },
      { token: accessToken, pinCode: pin, base: apiBase },
    );
  }
  await page.goto("/eleven", { waitUntil: "domcontentloaded" });
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

async function assertNotPinScreen(page) {
  await expect(page.getByText(/Enter your 4-digit PIN/i)).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: /Main/i })).toBeVisible();
}

test("v11 captures", async ({ browser }) => {
  test.setTimeout(600_000);
  fs.mkdirSync(OUT, { recursive: true });
  const shots: string[] = [];
  for (const stack of STACKS) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
    const page = await ctx.newPage();
    page.on("dialog", (d) => d.dismiss());
    await login(page, stack.email);
    for (const p of PAGES) {
      await page.goto(p.path, { waitUntil: "domcontentloaded", timeout: 60000 });
      await unlockPin(page);
      await expect(page.getByText(p.ready).first()).toBeVisible({ timeout: 25000 });
      await page.waitForTimeout(1500);
      await assertNotPinScreen(page);
      const file = path.join(OUT, `v11-${stack.state}-${p.slug}.png`);
      await page.screenshot({ path: file, fullPage: true });
      shots.push(file);
    }
    await ctx.close();
  }
  fs.writeFileSync(path.join(OUT, "v11-capture-list.json"), JSON.stringify(shots, null, 2));
});