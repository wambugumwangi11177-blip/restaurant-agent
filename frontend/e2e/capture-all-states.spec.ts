import { test, expect, chromium } from "@playwright/test";
import fs from "fs";
import path from "path";

const BASE_URL = "https://frontend-test-production-752b1b7c.up.railway.app";
const API_URL = process.env.BACKEND_TEST_URL || "https://backend-test-production-05524237.up.railway.app";
const ARTIFACTS = "/opt/cursor/artifacts";

const OWNER_PASSWORD = process.env.OWNER_PASSWORD || "VOpyWqNTRSnvaSS1";
const STAFF_PASSWORD = process.env.SEED_STAFF_PASSWORD || "JackTestPass1!";

const EMPTY_OWNER = "owner-empty@eleven.leviii";
const DATA_OWNER = "owner@eleven.leviii";
const EMPTY_JACK = "jack-empty@eleven.leviii";
const DATA_JACK = "jack@eleven.leviii";
const EMPTY_AMINA = "amina-empty@eleven.leviii";
const DATA_AMINA = "amina@eleven.leviii";

type Shot = { prefix: "empty" | "data"; role: string; page: string; path: string; marker: RegExp };

const SHOTS: Shot[] = [
  { prefix: "empty", role: "owner", page: "home", path: "/eleven", marker: /Needs you|Nothing needs you/i },
  { prefix: "empty", role: "owner", page: "money", path: "/eleven/money", marker: /Money|P&L|bill/i },
  { prefix: "empty", role: "owner", page: "stock", path: "/eleven/stock", marker: /Stock|run out|gap/i },
  { prefix: "empty", role: "owner", page: "team", path: "/eleven/staff", marker: /Staff|storekeeper|floor team/i },
  { prefix: "empty", role: "owner", page: "dishes", path: "/eleven/dishes", marker: /Dish|No dishes|recipe/i },
  { prefix: "empty", role: "owner", page: "alerts", path: "/eleven/alerts", marker: /Alert|No urgent/i },
  { prefix: "empty", role: "owner", page: "handovers", path: "/eleven/handovers", marker: /Handover|No handovers/i },
  { prefix: "empty", role: "owner", page: "more", path: "/eleven/more", marker: /More|Staff|Import/i },

  { prefix: "empty", role: "jack", page: "shift", path: "/store", marker: /Before the floor|setup|Today/i },
  { prefix: "empty", role: "jack", page: "deliveries", path: "/store/deliveries", marker: /Deliver|locked|questions/i },
  { prefix: "empty", role: "jack", page: "stock", path: "/store/stock", marker: /Stock|recipe|account/i },
  { prefix: "empty", role: "jack", page: "team", path: "/store/team", marker: /Team|Loading|pattern/i },
  { prefix: "empty", role: "jack", page: "me", path: "/store/account", marker: /Account|PIN|password/i },
  { prefix: "empty", role: "jack", page: "prep", path: "/store/prep", marker: /Prep|setup questions/i },
  { prefix: "empty", role: "jack", page: "restock", path: "/store/restock", marker: /restock|Low stock/i },
  { prefix: "empty", role: "jack", page: "questions", path: "/store/questions", marker: /order stock|Your answers|Loading/i },

  { prefix: "empty", role: "accountant", page: "home", path: "/store", marker: /Before the floor|setup|Today/i },
  { prefix: "empty", role: "accountant", page: "invoice-prices", path: "/store/invoice-prices", marker: /invoice|deliveries|No deliveries/i },
  { prefix: "empty", role: "accountant", page: "bills", path: "/store/costs", marker: /Bills|locked|Regular bills/i },

  { prefix: "data", role: "owner", page: "home", path: "/eleven", marker: /Needs you|Stock|Money/i },
  { prefix: "data", role: "owner", page: "money", path: "/eleven/money", marker: /Net|KES|P&L/i },
  { prefix: "data", role: "owner", page: "stock", path: "/eleven/stock", marker: /Stock|run out/i },
  { prefix: "data", role: "owner", page: "team", path: "/eleven/staff", marker: /Staff|Jack|setup/i },
  { prefix: "data", role: "owner", page: "dishes", path: "/eleven/dishes", marker: /Pilau|Dish|Plates/i },
  { prefix: "data", role: "owner", page: "alerts", path: "/eleven/alerts", marker: /Alert|needs you|bill/i },
  { prefix: "data", role: "owner", page: "handovers", path: "/eleven/handovers", marker: /Handover|Jack|Chef/i },
  { prefix: "data", role: "owner", page: "more", path: "/eleven/more", marker: /More|Staff|Handover/i },

  { prefix: "data", role: "jack", page: "shift", path: "/store", marker: /Today|Zone photos|Deliveries/i },
  { prefix: "data", role: "jack", page: "deliveries", path: "/store/deliveries", marker: /Supplier|delivery|invoice/i },
  { prefix: "data", role: "jack", page: "stock", path: "/store/stock", marker: /Stock|Rice|item/i },
  { prefix: "data", role: "jack", page: "team", path: "/store/team", marker: /Team|floor|pattern/i },
  { prefix: "data", role: "jack", page: "me", path: "/store/account", marker: /Account|PIN|email/i },
  { prefix: "data", role: "jack", page: "prep", path: "/store/prep", marker: /Prep|issue|Nothing to issue/i },
  { prefix: "data", role: "jack", page: "restock", path: "/store/restock", marker: /restock|Rice|WhatsApp/i },
  { prefix: "data", role: "jack", page: "questions", path: "/store/questions", marker: /Your answers|order stock/i },

  { prefix: "data", role: "accountant", page: "home", path: "/store", marker: /Today|Bills|Deliveries/i },
  { prefix: "data", role: "accountant", page: "invoice-prices", path: "/store/invoice-prices", marker: /Fresh Farm|invoice|Price per unit/i },
  { prefix: "data", role: "accountant", page: "bills", path: "/store/costs", marker: /Regular bills|Rent|KPLC/i },
];

const RAW_PATH = /\/store\/|\/eleven\//;

async function login(page: import("@playwright/test").Page, email: string, password: string) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  const loginResponse = page.waitForResponse(
    (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
    { timeout: 30000 },
  );
  await page.locator('button[type="submit"]').click();
  const response = await loginResponse;
  if (!response.ok()) throw new Error(`login failed ${response.status()}`);
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 30000 });
  await page.waitForFunction(() => (window.sessionStorage.getItem("access_token") || "").length > 20, { timeout: 15000 });
  await page.evaluate(() => {
    window.sessionStorage.setItem("app_pin_unlocked", "1");
    window.sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
}

async function assertNoRibs(page: import("@playwright/test").Page) {
  const bg = await page.evaluate(() => {
    const el = document.querySelector(".owner-glass-theme, .leviii-hearth-bg");
    if (!el) return "";
    return getComputedStyle(el, "::before").backgroundImage || "";
  });
  expect(bg.toLowerCase()).not.toContain("repeating");
}

const JACK_UNLOCK: [string, string][] = [
  ["ordering_method", "owner_approves"],
  ["receives_deliveries", "yes"],
  ["supplier_list", "listed"],
  ["stock_in_pos", "no"],
  ["issues_to_kitchen", "yes"],
  ["records_waste", "yes"],
  ["closes_the_day", "me"],
  ["knows_running_costs", "knows_payer"],
  ["zones", "listed"],
  ["buying_units", "no"],
  ["handover_who", "chef_pin"],
  ["handover_when", "lunch_dinner"],
  ["has_scale", "no"],
  ["waste_approver", "owner"],
  ["count_rhythm", "daily_pair"],
  ["par_and_max", "per_item"],
  ["who_pays", "accountant"],
  ["prep_ahead", "yes"],
  ["portions", "measured"],
];

async function ensureDataJackUnlocked(page: import("@playwright/test").Page) {
  const token = await page.evaluate(() => window.sessionStorage.getItem("access_token") || "");
  for (const [question_id, value] of JACK_UNLOCK) {
    const body: Record<string, unknown> = { question_id, value };
    if (question_id === "supplier_list") {
      body.suppliers = [{ name: "Fresh Farm", brings: "produce", arrival: "phone" }];
    }
    await page.request.post(`${API_URL}/api/v1/staff-setup/questionnaire`, {
      headers: { Authorization: `Bearer ${token}` },
      data: body,
    });
  }
}

test.describe.configure({ mode: "serial" });

test("capture empty and data mobile states", async () => {
  fs.mkdirSync(ARTIFACTS, { recursive: true });

  const browser = await chromium.launch();

  async function captureSet(
    creds: { owner: string; jack: string; accountant: string },
    prefix: "empty" | "data",
    beforeJack?: (page: import("@playwright/test").Page) => Promise<void>,
  ) {
    const roles: { key: "owner" | "jack" | "accountant"; email: string }[] = [
      { key: "owner", email: creds.owner },
      { key: "jack", email: creds.jack },
      { key: "accountant", email: creds.accountant },
    ];

    for (const { key, email } of roles) {
      const ctx = await browser.newContext({ baseURL: BASE_URL, serviceWorkers: "block" });
      const page = await ctx.newPage();
      await login(page, email, key === "owner" ? OWNER_PASSWORD : STAFF_PASSWORD);
      if (key === "jack" && beforeJack) await beforeJack(page);

      const roleShots = SHOTS.filter((s) => s.prefix === prefix && s.role === key);
      for (const shot of roleShots) {
        await page.goto(shot.path, { waitUntil: "domcontentloaded" });
        await page.waitForTimeout(1200);
        await expect(page.locator("body")).not.toContainText(RAW_PATH);
        await expect(page.locator("body")).toContainText(shot.marker, { timeout: 20000 });
        await assertNoRibs(page);
        const file = `${shot.prefix}-${shot.role}-${shot.page}.png`;
        await page.screenshot({ path: path.join(ARTIFACTS, file), fullPage: false, timeout: 15000 });
      }
      await ctx.close();
    }
  }

  await captureSet(
    { owner: EMPTY_OWNER, jack: EMPTY_JACK, accountant: EMPTY_AMINA },
    "empty",
  );

  await captureSet(
    { owner: DATA_OWNER, jack: DATA_JACK, accountant: DATA_AMINA },
    "data",
    ensureDataJackUnlocked,
  );

  await browser.close();
});