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
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 90000 });
}

async function logout(page: Page) {
  await page.goto("/store/account", { waitUntil: "networkidle" });
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

const ANSWERS: Record<string, RegExp> = {
  ordering_method: /owner approves/i,
  receives_deliveries: /^yes$/i,
  supplier_list: /save suppliers/i,
  stock_in_pos: /^no$/i,
  issues_to_kitchen: /^yes$/i,
  records_waste: /^yes$/i,
  closes_the_day: /^i do$/i,
  knows_running_costs: /^no$/i,
  zones: /main store, cold room/i,
  buying_units: /^no$/i,
  handover_who: /chef signs/i,
  handover_when: /once a day/i,
  has_scale: /^yes$/i,
  waste_approver: /^owner$/i,
  count_rhythm: /weekly/i,
  par_and_max: /i'll set each item/i,
  who_pays: /accountant pays/i,
  prep_ahead: /^no$/i,
  portions: /measured/i,
};

async function answerNextQuestion(page: Page, token: string) {
  const setup = await (await apiGet(page.request, token, "/api/v1/staff-setup")).json();
  const done = new Set((setup.answers || []).map((a: { question_id: string }) => a.question_id));
  const qstep = (setup.steps || []).find((s: { id: string }) => s.id === "questionnaire");
  const pending = (qstep?.questions || []).find((q: { id: string }) => !done.has(q.id));
  if (!pending) return false;
  await page.goto("/store/questions", { waitUntil: "networkidle" });
  if (pending.id === "supplier_list") {
    await page.locator('input[type="text"]').first().fill("Deep E2E Supply");
    await page.getByRole("button", { name: /save suppliers/i }).click();
    await page.waitForTimeout(800);
    log("questions", "supplier_list", "saved");
    return true;
  }
  const pattern = ANSWERS[pending.id];
  if (!pattern) throw new Error(`missing answer map for ${pending.id}`);
  await page.getByRole("button", { name: pattern }).first().click();
  await page.waitForTimeout(600);
  if (!page.url().includes("/store/questions")) await page.goto("/store/questions", { waitUntil: "networkidle" });
  log("questions", pending.id, "answered");
  return true;
}

test("jack deep journey jack-empty", async ({ browser }) => {
  test.setTimeout(900_000);
  test.skip(!TEMP, "SEED_STAFF_PASSWORD required");
  fs.mkdirSync(OUT, { recursive: true });
  if (RESET_KEY) {
    const reset = await fetch(`${API}/api/v1/test/jack-empty/reset`, {
      method: "POST",
      headers: { "X-Test-Stack-Key": RESET_KEY },
    });
    log("00-reset", "POST reset", reset.ok ? "ok" : `HTTP ${reset.status}`, reset.ok);
    expect(reset.ok).toBeTruthy();
  }

  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    serviceWorkers: "block",
  });
  const page = await ctx.newPage();

  // 1 Account
  await login(page, JACK, TEMP);
  await page.goto("/store/account", { waitUntil: "networkidle" });
  await shot(page, "01-account-form");
  await page.locator('input[autocomplete="current-password"]').fill(TEMP);
  await page.locator('input[autocomplete="new-password"]').fill(NEW_PASS);
  await page.locator('input[pattern="\\d{4}"]').fill(PIN);
  await page.getByRole("button", { name: /save password/i }).click();
  await page.waitForURL(/\/store\/questions/, { timeout: 60000 });
  let token = await tokenFrom(page);
  const me1 = await (await apiGet(page.request, token!, "/api/v1/auth/me")).json();
  expect(me1.must_change_password).toBe(false);
  expect(me1.has_pin).toBe(true);
  log("01-account", "staff-setup/account", "ok");

  await logout(page);
  await login(page, JACK, NEW_PASS);
  log("01-account", "re-login new password", "ok");
  await shot(page, "02-after-relogin");

  // 2 Questions (with reload resume)
  token = await tokenFrom(page);
  let answered = 0;
  while (answered < 8 && (await answerNextQuestion(page, token!))) answered += 1;
  await page.reload();
  await shot(page, "03-questions-resume");
  for (let guard = 0; guard < 24; guard += 1) {
    if (!(await answerNextQuestion(page, token!))) break;
  }
  const setupDone = await (await apiGet(page.request, token!, "/api/v1/staff-setup")).json();
  expect(setupDone.steps.find((s: { id: string }) => s.id === "questionnaire")?.state).toBe("done");
  await shot(page, "04-questions-done");
  await clickVisibleButtons(page, "04-questions");

  // 3 Recipes
  await page.goto("/store/recipes", { waitUntil: "networkidle" });
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
  await page.goto("/store/stock", { waitUntil: "networkidle" });
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
  await page.goto("/store/day-photos", { waitUntil: "networkidle" });
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
  await page.goto("/store/deliveries", { waitUntil: "networkidle" });
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
  await page.goto("/store/chefs", { waitUntil: "networkidle" });
  await page.getByLabel(/^name/i).fill("Chef Deep");
  await page.getByLabel(/^pin/i).fill(CHEF_PIN);
  await page.getByRole("button", { name: /add chef/i }).click();
  await page.goto("/store/issue", { waitUntil: "networkidle" });
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
  await page.goto("/store/waste", { waitUntil: "networkidle" });
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
  await page.goto("/store/restock", { waitUntil: "networkidle" });
  await shot(page, "12-restock-jack");
  const jackInbox = await (await apiGet(page.request, token!, "/api/v1/store/approval-inbox")).json();
  log("12-restock", "jack inbox", JSON.stringify(jackInbox.pending?.length ?? 0));

  if (OWNER_PASS) {
    const ownerCtx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const ownerPage = await ownerCtx.newPage();
    await login(ownerPage, OWNER, OWNER_PASS);
    await ownerPage.goto("/eleven", { waitUntil: "networkidle" });
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
    await page.goto(route, { waitUntil: "networkidle" });
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