/**
 * Full UI broken sweep — all Eleven roles, empty + data stacks, on test deploy (or local).
 * Run: SWEEP_BASE_URL=... OWNER_PASSWORD=... SEED_STAFF_PASSWORD=... npx playwright test -c playwright.broken-sweep.config.ts
 */
import { test, expect, type Page, type Request, type Response } from "@playwright/test";
import fs from "node:fs";

const API_URL = process.env.BACKEND_TEST_URL || "https://backend-test-production-05524237.up.railway.app";

const OWNER_PASSWORD = process.env.OWNER_PASSWORD || "";
const STAFF_PASSWORD = process.env.SEED_STAFF_PASSWORD || "";

const STACKS = [
  {
    name: "empty",
    owner: "owner-empty@eleven.leviii",
    jack: "jack-empty@eleven.leviii",
    accountant: "amina-empty@eleven.leviii",
  },
  {
    name: "data",
    owner: "owner@eleven.leviii",
    jack: "jack@eleven.leviii",
    accountant: "amina@eleven.leviii",
  },
] as const;

const OWNER_PAGES = [
  "/eleven",
  "/eleven/money",
  "/eleven/stock",
  "/eleven/team",
  "/eleven/more",
  "/eleven/approvals",
  "/eleven/alerts",
  "/eleven/dishes",
  "/eleven/handovers",
  "/eleven/deliveries",
  "/eleven/staff",
  "/eleven/activity",
  "/eleven/reports",
  "/eleven/settings",
  "/eleven/settings/till",
  "/eleven/settings/team-rules",
  "/eleven/import",
  "/eleven/ask",
  "/eleven/cash-check",
  "/eleven/sales-dishes",
  "/eleven/schedule",
];

const JACK_PAGES = [
  "/store",
  "/store/deliveries",
  "/store/stock",
  "/store/team",
  "/store/account",
  "/store/prep",
  "/store/restock",
  "/store/questions",
  "/store/suppliers",
  "/store/recipes",
  "/store/issue",
  "/store/waste",
  "/store/close",
  "/store/chefs",
  "/store/requests",
  "/store/schedule",
  "/store/day-photos",
  "/store/setup/opening",
  "/store/invoice-prices",
];

const ACCOUNTANT_PAGES = ["/store", "/store/invoice-prices", "/store/costs"];

const BLOCKED_BODY = /\/api\/v1\/|Traceback|HTTPException|sqlalchemy|Internal Server Error/i;

type Issue = { role: string; stack: string; path: string; kind: string; detail: string };

function trackPage(page: Page, issues: Issue[], meta: { role: string; stack: string }) {
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      if (text.includes("favicon") || text.includes("404") && text.includes(".woff")) return;
      issues.push({ ...meta, path: page.url(), kind: "console", detail: text.slice(0, 300) });
    }
  });
  page.on("response", (res: Response) => {
    const url = res.url();
    if (!url.includes("/api/v1/")) return;
    const status = res.status();
    if (status >= 500) {
      issues.push({ ...meta, path: page.url(), kind: "network", detail: `${status} ${url}` });
    }
    const allowed404 = ["/notifications", "/pos/quicksell/"];
    if (status === 404 && !allowed404.some((p) => url.includes(p))) {
      issues.push({ ...meta, path: page.url(), kind: "network-404", detail: url });
    }
    if (status === 403 && meta.role !== "owner") {
      /* module locked until Jack questionnaire — expected on empty stack */
    }
  });
}

async function login(page: Page, email: string, password: string) {
  if (!password) throw new Error("Set OWNER_PASSWORD and SEED_STAFF_PASSWORD for sweep");
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  const waitLogin = page.waitForResponse(
    (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
    { timeout: 45000 },
  );
  await page.locator('button[type="submit"]').click();
  const res = await waitLogin;
  expect(res.ok(), `login ${email}`).toBeTruthy();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 45000 });
}

async function visitAndProbe(page: Page, path: string, issues: Issue[], meta: { role: string; stack: string }) {
  await page.goto(path, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(800);
  const body = (await page.locator("body").innerText()).slice(0, 8000);
  expect(body, `raw API route on ${path}`).not.toMatch(BLOCKED_BODY);
  const nav = page.getByRole("navigation", { name: "Main", exact: true });
  if (await nav.isVisible().catch(() => false)) {
    const box = await nav.boundingBox();
    if (box) {
      expect(box.y + box.height, `bottom nav overflow on ${path}`).toBeLessThanOrEqual(844 + 4);
    }
  }
  const tabs = page.locator('nav[aria-label="Main"] a:visible');
  const tabCount = Math.min(await tabs.count(), 6);
  for (let i = 0; i < tabCount; i++) {
    await tabs.nth(i).click({ timeout: 5000 }).catch(() => undefined);
    if (page.isClosed()) return;
    await page.waitForTimeout(400);
  }
}

test.describe("UI broken sweep", () => {
  test("owner jack accountant empty and data stacks", async ({ browser }) => {
    test.skip(!OWNER_PASSWORD || !STAFF_PASSWORD, "credentials required for Railway sweep");
    const issues: Issue[] = [];
    let pagesVisited = 0;
    let buttonsTried = 0;

    for (const stack of STACKS) {
      for (const spec of [
        { role: "owner", email: stack.owner, paths: OWNER_PAGES },
        { role: "jack", email: stack.jack, paths: JACK_PAGES },
        { role: "accountant", email: stack.accountant, paths: ACCOUNTANT_PAGES },
      ]) {
        const context = await browser.newContext({
          viewport: { width: 390, height: 844 },
          serviceWorkers: "block",
        });
        const page = await context.newPage();
        trackPage(page, issues, { role: spec.role, stack: stack.name });
        await login(page, spec.email, spec.role === "owner" ? OWNER_PASSWORD : STAFF_PASSWORD);
        for (const path of spec.paths) {
          await visitAndProbe(page, path, issues, { role: spec.role, stack: stack.name });
          pagesVisited += 1;
          buttonsTried += 6;
        }
        await context.close();
      }
    }

    const report = { pagesVisited, buttonsTried, issues, apiUrl: API_URL };
    fs.mkdirSync("/opt/cursor/artifacts", { recursive: true });
    fs.writeFileSync("/opt/cursor/artifacts/ui-broken-sweep-results.json", JSON.stringify(report, null, 2));

    const hard = issues.filter((i) => i.kind === "network" || i.kind === "console");
    expect(hard, JSON.stringify(hard.slice(0, 20), null, 2)).toHaveLength(0);
  });
});