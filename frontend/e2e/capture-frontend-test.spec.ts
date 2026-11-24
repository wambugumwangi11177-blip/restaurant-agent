import { test, expect, chromium } from "@playwright/test";
import fs from "fs";
import path from "path";

const BASE_URL = "https://frontend-test-production-752b1b7c.up.railway.app";
const API_URL = process.env.BACKEND_TEST_URL || "https://backend-test-production-05524237.up.railway.app";
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
  "jack-wizard-step-2",
  "jack-setup-answers",
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
  "jack-wizard-step-2": "/store/questions",
  "jack-setup-answers": "/store/questions",
  "jack-restock-whatsapp": "/store/restock",
  "store-prep-list": "/store/prep",
  "accountant-invoice-prices": "/store/invoice-prices",
};

const PAGE_MARKERS: Partial<Record<(typeof TARGETS)[number], RegExp>> = {
  "owner-home": /needs you|Stock|Money|Eleven/i,
  "owner-dishes": /Dish|Pilau|recipe/i,
  "owner-money": /till|Profit|Money|Rent|Net|margin/i,
  "owner-alerts": /Alert|attention|approval/i,
  "owner-handover-timeline": /Handover|Chef|kitchen/i,
  "jack-wizard-step-1": /How do you order stock today/i,
  "jack-wizard-step-2": /suppliers arrive|How supplies arrive/i,
  "jack-setup-answers": /Your answers|How do you order stock/i,
  "jack-restock-whatsapp": /WhatsApp|wa\.me|Fresh Farm|8 kg Rice/i,
  "store-prep-list": /Prep for|ingredient|Pilau|prep quantities|Nothing to issue/i,
  "accountant-invoice-prices": /invoice|price|supplier|Fresh Farm/i,
};

type SavedSession = {
  cookies: [];
  origins: { origin: string; localStorage: []; sessionStorage: { name: string; value: string }[] }[];
};

function stateLooksValid(statePath: string): boolean {
  if (!fs.existsSync(statePath)) return false;
  try {
    const raw = JSON.parse(fs.readFileSync(statePath, "utf8")) as SavedSession;
    return (raw.origins ?? []).some((o) =>
      o.origin === BASE_URL && (o.sessionStorage ?? []).some((e) => e.name === "access_token" && e.value.length > 20),
    );
  } catch {
    return false;
  }
}

async function saveSession(statePath: string, page: import("@playwright/test").Page) {
  const token = await page.evaluate(() => window.sessionStorage.getItem("access_token") || "");
  const payload: SavedSession = {
    cookies: [],
    origins: [{ origin: BASE_URL, localStorage: [], sessionStorage: [{ name: "access_token", value: token }] }],
  };
  fs.writeFileSync(statePath, JSON.stringify(payload, null, 2));
  expect(stateLooksValid(statePath)).toBeTruthy();
}

function readAccessToken(statePath: string): string | null {
  try {
    const raw = JSON.parse(fs.readFileSync(statePath, "utf8")) as SavedSession;
    const entry = raw.origins?.[0]?.sessionStorage?.find((e) => e.name === "access_token");
    return entry?.value || null;
  } catch {
    return null;
  }
}

async function primeSession(page: import("@playwright/test").Page, statePath: string) {
  const token = readAccessToken(statePath);
  if (!token) throw new Error(`missing token in ${statePath}`);
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => {
    window.sessionStorage.setItem("access_token", t);
    window.sessionStorage.setItem("app_pin_unlocked", "1");
    window.sessionStorage.setItem("app_last_activity", String(Date.now()));
  }, token);
}

const OWNER_PIN = process.env.SEED_OWNER_PIN || "2468";
const STAFF_PIN = process.env.SEED_STAFF_PIN || "1357";

async function tapPin(page: import("@playwright/test").Page, digits: string) {
  for (const digit of digits) {
    await page.getByRole("button", { name: digit, exact: true }).click({ timeout: 5000 });
  }
}

async function settleAppLock(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    window.sessionStorage.setItem("app_pin_unlocked", "1");
    window.sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
  const choosePin = page.getByText(/Choose a PIN/i);
  if (await choosePin.isVisible({ timeout: 1500 }).catch(() => false)) {
    const pin = (await page.getByRole("heading").first().innerText()).includes("Jack") ? STAFF_PIN : OWNER_PIN;
    for (let round = 0; round < 2; round++) {
      for (const digit of pin) {
        await page.getByRole("button", { name: digit, exact: true }).click({ timeout: 10000 });
        await page.waitForTimeout(120);
      }
      await page.waitForTimeout(500);
    }
  }
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

async function resetJackQuestionnaire(page: import("@playwright/test").Page) {
  const token = await page.evaluate(() => window.sessionStorage.getItem("access_token") || "");
  const response = await page.request.post(`${API_URL}/api/v1/staff-setup/questionnaire/reset-self`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(`reset questionnaire: ${response.status()} ${await response.text()}`);
  }
}

async function postJackAnswer(page: import("@playwright/test").Page, question_id: string, value: string, suppliers?: object[]) {
  const token = await page.evaluate(() => window.sessionStorage.getItem("access_token") || "");
  const body: Record<string, unknown> = { question_id, value };
  if (suppliers) body.suppliers = suppliers;
  const response = await page.request.post(`${API_URL}/api/v1/staff-setup/questionnaire`, {
    headers: { Authorization: `Bearer ${token}` },
    data: body,
  });
  if (!response.ok() && response.status() !== 409) {
    throw new Error(`questionnaire ${question_id}: ${response.status()} ${await response.text()}`);
  }
}

async function completeJackQuestionnaire(page: import("@playwright/test").Page) {
  const token = await page.evaluate(() => window.sessionStorage.getItem("access_token") || "");
  for (const [question_id, value] of JACK_UNLOCK) {
    const body: Record<string, unknown> = { question_id, value };
    if (question_id === "supplier_list") {
      body.suppliers = [{ name: "Fresh Farm", brings: "produce", arrival: "phone" }];
    }
    const response = await page.request.post(`${API_URL}/api/v1/staff-setup/questionnaire`, {
      headers: { Authorization: `Bearer ${token}` },
      data: body,
    });
    if (!response.ok() && response.status() !== 409) {
      throw new Error(`questionnaire ${question_id}: ${response.status()} ${await response.text()}`);
    }
  }
}

async function answerVisibleQuestion(page: import("@playwright/test").Page): Promise<boolean> {
  await page.waitForTimeout(350);
  const saveSuppliers = page.getByRole("button", { name: /Save suppliers/i });
  if (await saveSuppliers.isVisible().catch(() => false)) {
    await page.locator("input").first().fill("Fresh Farm");
    await saveSuppliers.click();
    return true;
  }
  const knowsPayer = page.getByRole("button", { name: /I know who pays it/i });
  if (await knowsPayer.isVisible().catch(() => false)) {
    await knowsPayer.click();
    return true;
  }
  const primary = page
    .getByRole("button", {
      name: /approve|Yes|I'll name|Main store|Chef signs|Before lunch|Owner|Daily with|I'll set each|Accountant pays|Yes — I'll name|Measured|no — I use photos/i,
    })
    .first();
  if (await primary.isVisible().catch(() => false)) {
    await primary.click();
    return true;
  }
  return false;
}

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
  if (!response.ok()) {
    const body = await response.text();
    throw new Error(body.slice(0, 200) || `login HTTP ${response.status()}`);
  }
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 30000 });
  await page.waitForFunction(() => (window.sessionStorage.getItem("access_token") || "").length > 20, {
    timeout: 15000,
  });
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
  expect(bg.toLowerCase()).not.toContain("strip");
}

async function assertAuthedPage(page: import("@playwright/test").Page, key: (typeof TARGETS)[number]) {
  expect(page.url(), `${key} should not be login`).not.toContain("/login");
  const token = await page.evaluate(() => window.sessionStorage.getItem("access_token"));
  expect(token && token.length > 20, `${key} missing access_token`).toBeTruthy();
  await expect(page.locator("body")).not.toContainText(/could not be loaded|could not load|No restock waiting/i);
  const marker = PAGE_MARKERS[key];
  if (marker) {
    await expect(page.locator("body")).toContainText(marker, { timeout: 20000 });
  }
}

test.describe.configure({ mode: "serial" });

test("capture frontend-test screenshots", async () => {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  fs.mkdirSync(ARTIFACTS, { recursive: true });

  for (const f of fs.readdirSync(ARTIFACTS)) {
    if (!f.endsWith(".png")) continue;
    const base = f.replace(/\.png$/, "");
    if (!(TARGETS as readonly string[]).includes(base)) {
      fs.unlinkSync(path.join(ARTIFACTS, f));
    }
  }
  for (const name of TARGETS) {
    const old = path.join(ARTIFACTS, `${name}.png`);
    if (fs.existsSync(old)) fs.unlinkSync(old);
  }

  const browser = await chromium.launch();
  const ownerState = path.join(STATE_DIR, "owner.json");
  const jackState = path.join(STATE_DIR, "jack.json");
  const aminaState = path.join(STATE_DIR, "amina.json");

  for (const file of [ownerState, jackState, aminaState]) {
    if (!stateLooksValid(file) && fs.existsSync(file)) fs.unlinkSync(file);
  }

  async function contextWith(storage?: string) {
    return browser.newContext({
      baseURL: BASE_URL,
      serviceWorkers: "block",
      storageState: storage && fs.existsSync(storage) ? storage : undefined,
    });
  }

  if (!stateLooksValid(ownerState)) {
    const ctx = await contextWith();
    const page = await ctx.newPage();
    await login(page, OWNER_EMAIL, OWNER_PASSWORD);
    await saveSession(ownerState, page);
    await ctx.close();
  }

  {
    const ctx = await contextWith(ownerState);
    const page = await ctx.newPage();
    await primeSession(page, ownerState);
    for (const key of ["owner-home", "owner-dishes", "owner-money", "owner-alerts", "owner-handover-timeline"] as const) {
      await page.goto(ROUTES[key], { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(1200);
      await settleAppLock(page);
      if (key === "owner-handover-timeline") {
        await page.locator("li img").first().waitFor({ state: "visible", timeout: 15000 });
        await page.waitForTimeout(800);
      }
      await assertAuthedPage(page, key);
      await assertNoRibs(page);
      await page.screenshot({ path: path.join(ARTIFACTS, `${key}.png`), fullPage: false, timeout: 15000 });
    }
    await ctx.close();
  }

  if (!stateLooksValid(jackState)) {
    const ctx = await contextWith();
    const page = await ctx.newPage();
    await login(page, JACK_EMAIL, STAFF_PASSWORD);
    await saveSession(jackState, page);
    await ctx.close();
  }

  {
    const ctx = await contextWith(jackState);
    const page = await ctx.newPage();
    await primeSession(page, jackState);
    await resetJackQuestionnaire(page);

    await page.goto(ROUTES["jack-wizard-step-1"], { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);
    await settleAppLock(page);
    await expect(page.getByRole("heading", { name: /How do you order stock today/i })).toBeVisible({ timeout: 15000 });
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "jack-wizard-step-1.png"), fullPage: false });

    await page.getByRole("button", { name: /owner approves/i }).click();
    await page.waitForTimeout(600);
    await page.getByRole("button", { name: /^Yes$/i }).click();
    await page.waitForTimeout(800);
    await page.goto(ROUTES["jack-wizard-step-2"], { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1000);
    await expect(page.getByText(/How supplies arrive/i)).toBeVisible({ timeout: 15000 });
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "jack-wizard-step-2.png"), fullPage: false });

    await completeJackQuestionnaire(page);
    await page.goto(ROUTES["jack-setup-answers"], { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);
    await settleAppLock(page);
    await expect(page.getByRole("heading", { name: /Your answers/i })).toBeVisible({ timeout: 15000 });
    await expect(page.locator("body")).not.toContainText(/\/store\/|\/eleven\//);
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "jack-setup-answers.png"), fullPage: false });

    await page.goto(ROUTES["jack-restock-whatsapp"], { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);
    await settleAppLock(page);
    await assertAuthedPage(page, "jack-restock-whatsapp");
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "jack-restock-whatsapp.png"), fullPage: false });
    await page.goto(ROUTES["store-prep-list"], { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);
    await settleAppLock(page);
    await assertAuthedPage(page, "store-prep-list");
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "store-prep-list.png"), fullPage: false });
    await ctx.close();
  }

  if (!stateLooksValid(aminaState)) {
    const ctx = await contextWith();
    const page = await ctx.newPage();
    await login(page, AMINA_EMAIL, STAFF_PASSWORD);
    await saveSession(aminaState, page);
    await ctx.close();
  }

  {
    const ctx = await contextWith(aminaState);
    const page = await ctx.newPage();
    await primeSession(page, aminaState);
    await page.goto(ROUTES["accountant-invoice-prices"], { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);
    await settleAppLock(page);
    await page
      .getByText(/Fresh Farm|Key unit price|invoice photo/i)
      .first()
      .waitFor({ state: "visible", timeout: 15000 })
      .catch(() => undefined);
    await page.waitForTimeout(400);
    await assertAuthedPage(page, "accountant-invoice-prices");
    await assertNoRibs(page);
    await page.screenshot({ path: path.join(ARTIFACTS, "accountant-invoice-prices.png"), fullPage: false });
    await ctx.close();
  }

  await browser.close();
});