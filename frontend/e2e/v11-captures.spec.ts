import { test } from "@playwright/test";
import fs from "node:fs";

const BASE = process.env.SWEEP_BASE_URL || "https://frontend-test-production-752b1b7c.up.railway.app";
const OUT = "/opt/cursor/artifacts";

const STACKS = [
  { state: "data", email: "owner@eleven.leviii" },
  { state: "empty", email: "owner-empty@eleven.leviii" },
] as const;

const PAGES = [
  { slug: "home", path: "/eleven" },
  { slug: "money", path: "/eleven/money" },
  { slug: "money-pnl", path: "/eleven/money/pnl" },
  { slug: "money-dishes", path: "/eleven/money/dishes" },
  { slug: "stock", path: "/eleven/stock" },
  { slug: "stock-suppliers", path: "/eleven/stock/suppliers" },
  { slug: "stock-prep", path: "/eleven/stock/prep" },
  { slug: "more", path: "/eleven/more" },
  { slug: "settings-reports", path: "/eleven/settings/reports" },
  { slug: "ask", path: "/eleven/ask" },
] as const;

async function login(page, email: string) {
  const pass = process.env.OWNER_PASSWORD || "";
  if (!pass) test.skip();
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(pass);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 60000 });
}

test("v11 captures", async ({ browser }) => {
  fs.mkdirSync(OUT, { recursive: true });
  for (const stack of STACKS) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
    const page = await ctx.newPage();
    page.on("dialog", (d) => d.dismiss());
    await login(page, stack.email);
    for (const p of PAGES) {
      await page.goto(p.path, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page.waitForTimeout(1200);
      await page.screenshot({ path: `${OUT}/v11-${stack.state}-${p.slug}.png`, fullPage: true });
    }
    await ctx.close();
  }
});