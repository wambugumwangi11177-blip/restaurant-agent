import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const OUT = "/cursor/stores/self/artifacts";
const API =
  process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app";
const JACK = "jack-empty@eleven.leviii";
const OWNER = "owner-empty@eleven.leviii";
const TEMP = process.env.SEED_STAFF_PASSWORD || "";
const OWNER_PASS = process.env.SEED_OWNER_PASSWORD || process.env.OWNER_PASSWORD || "";
const RESET_KEY = process.env.TEST_STACK_RESET_KEY || "";
const NEW_PASS = `JackDeepE2E!${Date.now().toString(36)}`;
const PIN = "8642";
const CHEF_PIN = "2468";

const JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAgP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=",
  "base64",
);

type LogRow = { step: string; action: string; result: string; pass: boolean };
const LOG: LogRow[] = [];

function log(step: string, action: string, result: string, pass = true) {
  LOG.push({ step, action, result, pass });
}

async function shot(page: Page, name: string) {
  const file = path.join(OUT, `jack-deep-${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  log(name, "screenshot", file);
}

async function tokenFrom(page: Page) {
  return page.evaluate(() => localStorage.getItem("token") || sessionStorage.getItem("access_token"));
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 90000 });
}

async function logout(page: Page) {
  await page.goto("/store/account", { waitUntil: "domcontentloaded" });
  const out = page.getByRole("button", { name: /sign out|log out|different account/i });
  if (await out.count()) {
    await out.first().click();
    log("logout", "click", "sign out");
  } else {
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.goto("/login");
    log("logout", "clear storage", "ok");
  }
}

async function apiGet(request: APIRequestContext, token: string, route: string) {
  return request.get(`${API}${route}`, { headers: { Authorization: `Bearer ${token}` } });
}

async function clickVisibleButtons(page: Page, step: string) {
  const buttons = page.locator("button:visible");
  const n = await buttons.count();
  for (let i = 0; i < n; i++) {
    const btn = buttons.nth(i);
    const label = ((await btn.innerText().catch(() => "")) || "").trim().replace(/\s+/g, " ").slice(0, 72);
    if (!label || /sign out|log out|hand it over|receive delivery|save waste/i.test(label)) continue;
    try {
      await btn.click({ timeout: 2000 });
      log(step, `button: ${label}`, "clicked");
    } catch {
      log(step, `button: ${label}`, "skip", true);
    }
  }
}

const QUESTION_VALUES: Record<string, string> = {
  ordering_method: "owner_approves",
  receives_deliveries: "yes",
  supplier_list: "listed",
  stock_in_pos: "no",
  issues_to_kitchen: "yes",
  records_waste: "yes",
  closes_the_day: "me",
  knows_running_costs: "no",
  zones: "listed",
  buying_units: "no",
  handover_who: "chef_pin",
  handover_when: "once",
  has_scale: "yes",
  waste_approver: "owner",
  count_rhythm: "weekly",
  par_and_max: "per_item",
  who_pays: "accountant",
  prep_ahead: "no",
  portions: "measured",
};

const UI_BUTTON: Record<string, RegExp> = {
  ordering_method: /owner approves/i,
  receives_deliveries: /^yes$/i,
  stock_in_pos: /^no$/i,
};

async function postQuestion(page: Page, token: string, questionId: string) {
  const value = QUESTION_VALUES[questionId];
  if (!value) throw new Error(`no value for ${questionId}`);
  const body: Record<string, unknown> = { question_id: questionId, value, suppliers: [] };
  if (questionId === "supplier_list") {
    body.suppliers = [{ name: "Deep E2E Supply", brings: "Main food", arrival: "phone" }];
  }
  const res = await page.request.post(`${API}/api/v1/staff-setup/questionnaire`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    data: body,
  });
  expect(res.ok()).toBeTruthy();
  log("questions", questionId, `HTTP ${res.status()}`);
}

async function answerQuestionUi(page: Page, questionId: string) {
  await page.goto("/store/questions", { waitUntil: "domcontentloaded" });
  if (questionId === "supplier_list") {
    await page.locator('input[type="text"]').first().fill("Deep E2E Supply");
    await page.getByRole("button", { name: /save suppliers/i }).click();
    log("questions-ui", questionId, "saved");
    return;
  }
  const pattern = UI_BUTTON[questionId];
  if (!pattern) throw new Error(`no UI map for ${questionId}`);
  await page.getByRole("button", { name: pattern }).first().click();
  log("questions-ui", questionId, "clicked");
}

test("jack deep journey jack-empty", async ({ browser }) => {
  test.setTimeout(600_000);
  test.skip(!TEMP, "SEED_STAFF_PASSWORD required");
  fs.mkdirSync(OUT, { recursive: true });
  if (RESET_KEY) {
    const reset = await fetch(`${API}/api/v1/test/jack-empty/reset`, {
      method: "POST",
      headers: { "X-Test-Stack-Key": RESET_KEY },
    });
    log("00-reset", "POST reset", reset.ok ? "ok" : `HTTP ${reset.status}`, reset.ok);
    if (!reset.ok) log("00-reset", "hint", "Deploy 869bdb0+ and set TEST_STACK_RESET_KEY on backend-test", false);
  } else {
    log("00-reset", "skip", "TEST_STACK_RESET_KEY not set — journey may skip first-login", true);
  }

  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    serviceWorkers: "block",
  });
  const page = await ctx.newPage();

  // 1 Account
  await login(page, JACK, TEMP);
  let token = await tokenFrom(page);
  let me1 = await (await apiGet(page.request, token!, "/api/v1/auth/me")).json();
  const needsAccount = Boolean(me1.must_change_password) || !me1.has_pin;
  let activePassword = TEMP;
  await page.goto("/store/account", { waitUntil: "domcontentloaded" });
  await shot(page, "01-account-form");
  const accountForm = page.locator('input[autocomplete="current-password"]');
  if (needsAccount) {
    if (await accountForm.isVisible().catch(() => false)) {
      await accountForm.fill(TEMP);
      await page.locator('input[autocomplete="new-password"]').fill(NEW_PASS);
      await page.locator('input[pattern="\\d{4}"]').fill(PIN);
      await page.getByRole("button", { name: /save password/i }).click();
      await page.waitForURL(/\/store\/questions/, { timeout: 60000 });
      log("01-account", "staff-setup/account ui", "ok");
    } else {
      const saveAcct = await page.request.post(`${API}/api/v1/staff-setup/account`, {
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        data: { current_password: TEMP, new_password: NEW_PASS, pin: PIN },
      });
      expect(saveAcct.ok()).toBeTruthy();
      log("01-account", "staff-setup/account api", "ok");
    }
    await logout(page);
    await login(page, JACK, NEW_PASS);
    activePassword = NEW_PASS;
    token = await tokenFrom(page);
    log("01-account", "re-login new password", "ok");
  } else {
    log("01-account", "skip", "already set (set TEST_STACK_RESET_KEY + redeploy for fresh first-login)");
  }
  await shot(page, "02-after-relogin");
  token = await tokenFrom(page);

  // 2 Questions (with reload resume)
  token = await tokenFrom(page);
  let setupDone = await (await apiGet(page.request, token!, "/api/v1/staff-setup")).json();
  const qState = setupDone.steps.find((s: { id: string }) => s.id === "questionnaire")?.state;
  if (qState !== "done") {
    const keys = Object.keys(QUESTION_VALUES);
    for (const qid of keys.slice(0, Math.ceil(keys.length / 2))) await postQuestion(page, token!, qid);
    await page.goto("/store/questions", { waitUntil: "domcontentloaded" });
    await page.reload();
    await shot(page, "03-questions-resume");
    for (const qid of keys.slice(Math.ceil(keys.length / 2))) await postQuestion(page, token!, qid);
    setupDone = await (await apiGet(page.request, token!, "/api/v1/staff-setup")).json();
    expect(setupDone.steps.find((s: { id: string }) => s.id === "questionnaire")?.state).toBe("done");
    await page.goto("/store/questions", { waitUntil: "domcontentloaded" });
    const change = page.getByRole("button", { name: /^change$/i }).first();
    if (await change.isVisible()) {
      await change.click();
      await page.getByRole("button", { name: /^yes$/i }).first().click();
      log("04-questions", "change answer ui", "ok");
    }
    setupDone = await (await apiGet(page.request, token!, "/api/v1/staff-setup")).json();
    expect(setupDone.steps.find((s: { id: string }) => s.id === "questionnaire")?.state).toBe("done");
  } else {
    log("04-questions", "skip", "already done");
  }
  await shot(page, "04-questions-done");
  await clickVisibleButtons(page, "04-questions");

  // 3 Recipes
  await page.goto("/store/recipes", { waitUntil: "domcontentloaded" });
  await page.locator('input[type="text"]').nth(0).fill("Deep Pilau");
  await page.locator('input[type="text"]').nth(1).fill("Rice");
  await page.getByRole("button", { name: /save recipe line/i }).click();
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: /^edit$/i }).first().click();
  await page.locator('input[type="text"]').nth(1).fill("Basmati Rice");
  await page.getByRole("button", { name: /save recipe line/i }).click();
  await page.getByRole("button", { name: /^delete$/i }).first().click();
  await page.locator('input[type="text"]').nth(0).fill("Deep Pilau");
  await page.locator('input[type="text"]').nth(1).fill("Rice");
  await page.getByRole("button", { name: /save recipe line/i }).click();
  await page.getByRole("button", { name: /these recipes are in/i }).click();
  await shot(page, "05-recipes");
  const recipes = await (await apiGet(page.request, token!, "/api/v1/store/recipes")).json();
  expect((recipes.dishes || []).length).toBeGreaterThan(0);
  log("05-recipes", "add edit delete finish", "ok");

  // 4 Stock + suppliers already from questionnaire
  await page.goto("/store/stock", { waitUntil: "domcontentloaded" });
  const itemField = page.getByLabel(/item/i);
  if (await itemField.isVisible()) {
    await itemField.fill("Deep Rice");
    await page.getByLabel(/^quantity/i).fill("4");
    await page.getByLabel(/^unit/i).fill("kg");
    await page.getByLabel(/par level/i).fill("20");
    await page.getByLabel(/reorder at/i).fill("6");
    const sup = page.getByLabel(/default supplier/i);
    if (await sup.count()) await sup.selectOption({ index: 1 });
    await page.getByRole("button", { name: /save opening count/i }).click();
    await page.waitForTimeout(800);
  }
  await shot(page, "06-stock");
  const items = await (await apiGet(page.request, token!, "/api/v1/store/items")).json();
  expect((items.items || []).some((i: { item_name: string }) => /rice/i.test(i.item_name))).toBeTruthy();
  log("06-stock", "opening count", "ok");

  // Day photos (open all zones)
  await page.goto("/store/day-photos", { waitUntil: "domcontentloaded" });
  const zones = await (await apiGet(page.request, token!, "/api/v1/store/day-photos/status")).json();
  for (const zone of zones.zones || []) {
    if (zone.open_done) continue;
    await page.locator("select").selectOption(String(zone.id));
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({ name: "zone.jpg", mimeType: "image/jpeg", buffer: JPEG });
    await page.getByRole("button", { name: /save open photo/i }).click();
    await page.waitForTimeout(500);
  }
  await shot(page, "07-day-photos");

  // 5 Delivery
  await page.goto("/store/deliveries", { waitUntil: "domcontentloaded" });
  await page.locator("select").first().selectOption({ index: 1 });
  await page.getByLabel(/^item/i).fill("Deep Rice");
  await page.getByLabel(/^quantity/i).fill("2");
  const inputs = page.locator('input[type="file"]');
  await inputs.nth(0).setInputFiles({ name: "invoice.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await inputs.nth(1).setInputFiles({ name: "goods.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await page.getByRole("button", { name: /receive delivery/i }).click();
  await page.waitForTimeout(1200);
  await shot(page, "08-deliveries");
  const deliveries = await (await apiGet(page.request, token!, "/api/v1/store/deliveries")).json();
  const latest = deliveries[0];
  expect(latest?.lines?.length).toBeGreaterThan(0);
  const photoId = latest?.photos?.[0]?.id ?? latest?.photos?.[0]?.photo_id;
  if (photoId && latest.id) {
    const photoRes = await apiGet(page.request, token!, `/api/v1/store/deliveries/${latest.id}/photos/${photoId}`);
    expect(photoRes.status()).toBe(200);
    log("08-deliveries", "photo GET", String(photoRes.status()));
  }

  // Chef + handover
  await page.goto("/store/chefs", { waitUntil: "domcontentloaded" });
  await page.getByLabel(/^name/i).fill("Chef Deep");
  await page.getByLabel(/^pin/i).fill(CHEF_PIN);
  await page.getByRole("button", { name: /add chef/i }).click();
  await page.goto("/store/issue", { waitUntil: "domcontentloaded" });
  await page.locator("select").first().selectOption({ index: 1 });
  await page.locator('input[inputmode="decimal"]').first().fill("1");
  await page.locator("select").nth(1).selectOption({ index: 1 });
  await page.locator('input[pattern="\\d{4}"]').fill("0000");
  const issuePhoto = page.locator('input[type="file"]').first();
  await issuePhoto.setInputFiles({ name: "handover.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await page.getByRole("button", { name: /hand it over/i }).click();
  await expect(page.getByText(/pin|not saved|incorrect/i)).toBeVisible({ timeout: 15000 });
  await shot(page, "09-handover-bad-pin");
  await page.locator('input[pattern="\\d{4}"]').fill(CHEF_PIN);
  await page.getByRole("button", { name: /hand it over/i }).click();
  await expect(page.getByText(/handed to the kitchen/i)).toBeVisible({ timeout: 20000 });
  await shot(page, "10-handover-ok");

  // Waste
  await page.goto("/store/waste", { waitUntil: "domcontentloaded" });
  await page.locator("select").first().selectOption({ index: 1 });
  await page.getByLabel(/^quantity/i).fill("0.1");
  await page.locator("select").nth(1).selectOption({ index: 1 });
  await page.locator('input[pattern="\\d{4}"]').fill(CHEF_PIN);
  await page.locator('input[type="file"]').first().setInputFiles({ name: "waste.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await page.getByRole("button", { name: /save waste/i }).click();
  await page.waitForTimeout(1000);
  await shot(page, "11-waste");

  // Restock draft
  await fetch(`${API}/api/v1/test/reorder-draft`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  await page.goto("/store/restock", { waitUntil: "domcontentloaded" });
  await shot(page, "12-restock-jack");
  const jackInbox = await (await apiGet(page.request, token!, "/api/v1/store/approval-inbox")).json();
  log("12-restock", "jack inbox", JSON.stringify(jackInbox.pending?.length ?? 0));

  if (OWNER_PASS) {
    const ownerCtx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const ownerPage = await ownerCtx.newPage();
    await login(ownerPage, OWNER, OWNER_PASS);
    await ownerPage.goto("/eleven", { waitUntil: "domcontentloaded" });
    await expect(ownerPage.getByRole("heading", { name: /needs you/i })).toBeVisible({ timeout: 45000 });
    await shot(ownerPage, "13-owner-needs-you");
    const approvals = await (await apiGet(ownerPage.request, await tokenFrom(ownerPage)!, "/api/v1/store/approvals")).json();
    const restock = (approvals.pending || []).find((p: { kind: string }) => p.kind === "restock");
    if (restock) {
      await ownerPage.request.post(`${API}/api/v1/store/approvals`, {
        headers: { Authorization: `Bearer ${await tokenFrom(ownerPage)}`, "Content-Type": "application/json" },
        data: { kind: "restock", id: restock.id, decision: "approve" },
      });
    }
    await ownerPage.goto("/store/requests");
    await ownerPage.goto("/eleven");
    await shot(ownerPage, "14-owner-after-approve");
    await ownerCtx.close();
    await page.reload();
    const waiting = await (await apiGet(page.request, token!, "/api/v1/store/approval-inbox")).json();
    const hasWait = (waiting.pending || []).some((r: { approval_card_title?: string }) =>
      /waiting on/i.test(r.approval_card_title || ""),
    );
    log("12-restock", "jack waiting", hasWait ? "Waiting on …" : String(waiting.pending?.[0]?.approval_card_title || "none"));
  }

  // Sweep store nav buttons
  for (const route of ["/store", "/store/requests", "/store/suppliers", "/store/prep", "/store/close"]) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    await clickVisibleButtons(page, route);
  }

  if (RESET_KEY) {
    const resetEnd = await fetch(`${API}/api/v1/test/jack-empty/reset`, {
      method: "POST",
      headers: { "X-Test-Stack-Key": RESET_KEY },
    });
    log("99-reset", "POST reset end", resetEnd.ok ? "ok" : `HTTP ${resetEnd.status}`, resetEnd.ok);
    expect(resetEnd.ok).toBeTruthy();
  }

  fs.writeFileSync(path.join(OUT, "jack-deep-click-log.json"), JSON.stringify(LOG, null, 2));
  await ctx.close();
});