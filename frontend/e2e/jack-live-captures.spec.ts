import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const STORE_OUT = "/cursor/stores/self/artifacts";
const LOG: { step: string; action: string; result: string }[] = [];

async function loginStore(page, email: string, password: string) {
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 60000 });
  LOG.push({ step: "1-login", action: "sign in", result: "ok" });
}

async function shot(page, name: string) {
  const file = path.join(STORE_OUT, `jack-live-${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  LOG.push({ step: name, action: "screenshot", result: file });
}

test("jack empty stack journey captures", async ({ browser }) => {
  test.setTimeout(300_000);
  const pass = process.env.SEED_STAFF_PASSWORD || "";
  if (!pass) test.skip();
  fs.mkdirSync(STORE_OUT, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
  const page = await ctx.newPage();
  await loginStore(page, "jack-empty@eleven.leviii", pass);
  await page.goto("/store", { waitUntil: "networkidle" });
  await shot(page, "01-store-home");
  await page.goto("/store/account", { waitUntil: "networkidle" });
  await shot(page, "02-account");
  LOG.push({ step: "2-account", action: "view set-password form", result: "visible" });
  await page.goto("/store/questions", { waitUntil: "networkidle" });
  await shot(page, "03-questions");
  await page.goto("/store/recipes", { waitUntil: "networkidle" });
  await shot(page, "04-recipes");
  await page.goto("/store/stock", { waitUntil: "networkidle" });
  await shot(page, "05-stock");
  await page.goto("/store/deliveries", { waitUntil: "networkidle" });
  await shot(page, "06-deliveries");
  await page.goto("/store/issue", { waitUntil: "networkidle" });
  await shot(page, "07-handover");
  await page.goto("/store/waste", { waitUntil: "networkidle" });
  await shot(page, "08-waste");
  await page.goto("/store/restock", { waitUntil: "networkidle" });
  await shot(page, "09-restock");
  const token = await page.evaluate(() => localStorage.getItem("token"));
  const items = await page.request.get(
    `${process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app"}/api/v1/store/items`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  const json = await items.json().catch(() => ({}));
  const leaked = Object.keys(json.items?.[0] || {}).filter((k) => /cost|price|kes|amount/i.test(k));
  LOG.push({ step: "money-strip", action: "GET /store/items", result: leaked.length ? `leaked ${leaked.join(",")}` : "no money keys" });
  expect(leaked).toEqual([]);
  fs.writeFileSync(path.join(STORE_OUT, "jack-live-click-log.json"), JSON.stringify(LOG, null, 2));
  await ctx.close();
});