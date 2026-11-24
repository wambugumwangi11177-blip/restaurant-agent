import { test, expect, chromium, type BrowserContext } from "@playwright/test";
import fs from "fs";
import path from "path";

const BASE_URL = "https://frontend-test-production-752b1b7c.up.railway.app";
const ARTIFACTS = "/opt/cursor/artifacts";
const STATE_DIR = path.join(ARTIFACTS, "playwright-state");

const OWNER_EMAIL = "owner@eleven.leviii";
const OWNER_PASSWORD = process.env.OWNER_PASSWORD || "VOpyWqNTRSnvaSS1";
const JACK_EMAIL = "jack@eleven.leviii";
const STAFF_PASSWORD = process.env.SEED_STAFF_PASSWORD || "JackTestPass1!";
const AMINA_EMAIL = "amina@eleven.leviii";

const TARGETS = [
  "owner-home",
  "owner-dishes",
  "owner-money",
  "owner-alerts",
  "owner-handover-timeline",
  "jack-wizard-step-1",
  "jack-restock-whatsapp",
  "store-prep-list",
  "accountant-invoice-prices",
] as const;

const ROUTES: Record<(typeof TARGETS)[number], string> = {
  "owner-home": "/eleven",
  "owner-dishes": "/eleven/dishes",
  "owner-money": "/eleven/money",
  "owner-alerts": "/eleven/alerts",
  "owner-handover-timeline": "/eleven/handovers",
  "jack-wizard-step-1": "/store/questions",
  "jack-restock-whatsapp": "/store/restock",
  "store-prep-list": "/store/prep",
  "accountant-invoice-prices": "/store/invoice-prices",
};

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

async function login(page: import("@playwright/test").Page, email: string, password: string) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 20000 });
}

async function assertNoRibs(page: import("@playwright/test").Page) {
  const bg = await page.evaluate(() => {
    const el = document.querySelector(".owner-glass-theme, .leviii-hearth-bg");
    if (!el) return "";
    return getComputedStyle(el, "::before").backgroundImage || "";
  });
  expect(bg.toLowerCase()).not.toContain("repeating");
  expect(bg.toLowerCase()).not.toContain("strip");
}

test.describe.configure({ mode: "serial" });

test("capture frontend-test screenshots", async () => {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  for (const name of TARGETS) {
    const old = path.join(ARTIFACTS, `${name}.png`);
    if (fs.existsSync(old)) fs.unlinkSync(old);
  }
  for (const f of fs.readdirSync(ARTIFACTS)) {
    if (f.endsWith("-login-failed.png") || f.startsWith("owner-") && !TARGETS.includes(f.replace(".png", "") as never)) {
      try {
        fs.unlinkSync(path.join(ARTIFACTS, f));
      } catch {
        /* ignore */
      }
    }
  }

  const browser = await chromium.launch();
  const ownerState = path.join(STATE_DIR, "owner.json");
  const jackState = path.join(STATE_DIR, "jack.json");
  const aminaState = path.join(STATE_DIR, "amina.json");

  async function contextWith(blockServiceWorker: boolean, storage?: string) {
    return browser.newContext({
      baseURL: BASE_URL,
      serviceWorkers: "block",
      storageState: storage,
    });
  }

  if (!fs.existsSync(ownerState)) {
    const ctx = await contextWith(true);
    const page = await ctx.newPage();
    await login(page, OWNER_EMAIL, OWNER_PASSWORD);
    await ctx.storageState({ path: ownerState });
    await ctx.close();
  }

  {
    const ctx = await contextWith(true, ownerState);
    const page = await ctx.newPage();
    for (const key of ["owner-home", "owner-dishes", "owner-money", "owner-alerts", "owner-handover-timeline"] as const) {
      await page.goto(ROUTES[key], { waitUntil: "networkidle" });
      await assertNoRibs(page);
      await page.screenshot({ path: path.join(ARTIFACTS, `${key}.png`), fullPage: true });
    }
    await ctx.close();
  }

  if (!fs.existsSync(jackState)) {
    const ctx = await contextWith(true);
    const page = await ctx.newPage();
    await login(page, JACK_EMAIL, STAFF_PASSWORD);
    await ctx.storageState({ path: jackState });
    await ctx.close();
  }

  {
    const ctx = await contextWith(true, jackState);
    const page = await ctx.newPage();
    await page.goto(ROUTES["jack-wizard-step-1"], { waitUntil: "networkidle" });
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "jack-wizard-step-1.png"), fullPage: true });

    for (const [qid, value] of JACK_UNLOCK) {
      await page.request.post("/api/v1/staff-setup/questionnaire", {
        data: { question_id: qid, value, suppliers: qid === "supplier_list" ? [{ name: "Fresh Farm", brings: "Main food", arrival: "phone" }] : undefined },
      });
    }
    await page.goto(ROUTES["jack-restock-whatsapp"], { waitUntil: "networkidle" });
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "jack-restock-whatsapp.png"), fullPage: true });
    await page.goto(ROUTES["store-prep-list"], { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(ARTIFACTS, "store-prep-list.png"), fullPage: true });
    await ctx.close();
  }

  if (!fs.existsSync(aminaState)) {
    const ctx = await contextWith(true);
    const page = await ctx.newPage();
    await login(page, AMINA_EMAIL, STAFF_PASSWORD);
    await ctx.storageState({ path: aminaState });
    await ctx.close();
  }

  {
    const ctx = await contextWith(true, aminaState);
    const page = await ctx.newPage();
    await page.goto(ROUTES["accountant-invoice-prices"], { waitUntil: "networkidle" });
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "accountant-invoice-prices.png"), fullPage: true });
    await ctx.close();
  }

  await browser.close();
});