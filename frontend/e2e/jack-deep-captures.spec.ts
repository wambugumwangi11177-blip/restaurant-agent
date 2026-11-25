import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const OUT = "/cursor/stores/self/artifacts";
const API =
  process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app";
const JACK = "jack-empty@eleven.leviii";
const OWNER = "owner-empty@eleven.leviii";
const TEMP = process.env.SEED_STAFF_PASSWORD || "";
const OWNER_PASS = process.env.SEED_OWNER_PASSWORD || process.env.OWNER_PASSWORD || "";
const RESET_KEY =
  process.env.TEST_STACK_RESET_KEY ||
  (fs.existsSync("/cursor/stores/self/test-stack-reset-key.txt")
    ? fs.readFileSync("/cursor/stores/self/test-stack-reset-key.txt", "utf8").trim()
    : "");
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

const MIN_SCREEN_STD = 8;

function pngStddev(file: string): number {
  return Number(
    execFileSync(
      "python3",
      [
        "-c",
        "from PIL import Image; import numpy as np, sys; a=np.array(Image.open(sys.argv[1]).convert('RGB')); print(float(a.std()))",
        file,
      ],
      { encoding: "utf8" },
    ).trim(),
  );
}

async function waitForStoreShell(page: Page) {
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  await expect(page.getByRole("navigation", { name: /store/i })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(/checking account access/i)).toHaveCount(0);
  await page.waitForFunction(
    () => {
      const main = document.querySelector("main");
      return (main?.textContent?.replace(/\s+/g, " ").trim().length ?? 0) > 24;
    },
    { timeout: 45_000 },
  );
}

async function waitForOwnerShell(page: Page) {
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  await expect(page.getByRole("navigation", { name: /main/i })).toBeVisible({ timeout: 45_000 });
  await page.waitForFunction(
    () => {
      const main = document.querySelector("main");
      return (main?.textContent?.replace(/\s+/g, " ").trim().length ?? 0) > 24;
    },
    { timeout: 45_000 },
  );
}

async function shot(page: Page, name: string, opts?: { owner?: boolean }) {
  if (opts?.owner) await waitForOwnerShell(page);
  else await waitForStoreShell(page);
  const file = path.join(OUT, `jack-deep-${name}.png`);
  await page.screenshot({ path: file, fullPage: true, animations: "disabled" });
  const std = pngStddev(file);
  expect(std, `${name} screenshot is blank (std=${std})`).toBeGreaterThan(MIN_SCREEN_STD);
  log(name, "screenshot", `${file} std=${std.toFixed(1)}`);
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

async function loginWithApi(page: Page, email: string, password: string, landing = "/eleven") {
  const res = await page.request.post(`${API}/api/v1/auth/login`, { data: { email, password } });
  expect(res.ok(), `login ${email} HTTP ${res.status()}`).toBeTruthy();
  const { access_token } = await res.json();
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.evaluate((token) => {
    localStorage.setItem("token", token);
    sessionStorage.setItem("access_token", token);
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  }, access_token);
  await page.goto(landing, { waitUntil: "domcontentloaded" });
}

async function unlockPinIfNeeded(page: Page, pin: string) {
  const lock = page.getByText(/Enter your 4-digit PIN/i);
  if (!(await lock.isVisible().catch(() => false))) {
    await page.evaluate(() => {
      sessionStorage.setItem("app_pin_unlocked", "1");
      sessionStorage.setItem("app_last_activity", String(Date.now()));
    });
    return;
  }
  const token = await tokenFrom(page);
  if (token) {
    await page.request.post(`${API}/api/v1/auth/pin/unlock`, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      data: { pin },
    });
  }
  const unlockWait = page.waitForResponse(
    (r) => r.url().includes("/auth/pin/unlock") && r.status() === 200,
    { timeout: 30000 },
  );
  const pad = page.getByLabel("PIN keypad");
  for (const digit of pin.split("")) {
    await pad.getByRole("button", { name: digit, exact: true }).click();
    await page.waitForTimeout(100);
  }
  await unlockWait.catch(() => undefined);
  await expect(lock).toBeHidden({ timeout: 30000 });
  await page.evaluate(() => {
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
  log("pin-unlock", "keypad", "ok");
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
    await page.getByRole("textbox").first().fill("Deep E2E Supply");
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
    expect(reset.ok, `reset HTTP ${reset.status}`).toBeTruthy();
  } else {
    log("00-reset", "skip", "TEST_STACK_RESET_KEY not set — journey may skip first-login", true);
  }

  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    serviceWorkers: "block",
  });
  await ctx.addInitScript(() => {
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
  const page = await ctx.newPage();

  // 1 Account
  await login(page, JACK, TEMP);
  let token = await tokenFrom(page);
  let me1 = await (await apiGet(page.request, token!, "/api/v1/auth/me")).json();
  const needsAccount = Boolean(me1.must_change_password) || !me1.has_pin;
  let activePassword = TEMP;
  await page.goto("/store/account", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("textbox", { name: /current password/i })).toBeVisible({ timeout: 45_000 });
  await shot(page, "01-account-form");
  const accountForm = page.locator('input[autocomplete="current-password"]');
  if (needsAccount) {
    if (await accountForm.isVisible().catch(() => false)) {
      await page.getByRole("textbox", { name: /current password/i }).fill(TEMP);
      await page.getByRole("textbox", { name: /new password/i }).fill(NEW_PASS);
      await page.getByRole("textbox", { name: /4-digit pin/i }).fill(PIN);
      await page.getByRole("button", { name: /save password and pin/i }).click();
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
    await unlockPinIfNeeded(page, PIN);
    activePassword = NEW_PASS;
    token = await tokenFrom(page);
    log("01-account", "re-login new password", "ok");
  } else {
    log("01-account", "skip", "already set (set TEST_STACK_RESET_KEY + redeploy for fresh first-login)");
  }
  await page.goto("/store", { waitUntil: "domcontentloaded" });
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
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator("main")).toContainText(/\d+ of \d+|who takes it|supplier|delivery|order/i, { timeout: 45_000 });
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
  await page.goto("/store/questions", { waitUntil: "domcontentloaded" });
  await expect(page.locator("main")).toContainText(/summary|change|done|saved|\d+ of \d+/i, { timeout: 45_000 });
  await shot(page, "04-questions-done");

  // 3 Recipes
  await page.goto("/store/recipes", { waitUntil: "domcontentloaded" });
  await unlockPinIfNeeded(page, PIN);
  await expect(page.getByRole("button", { name: /save recipe line/i })).toBeVisible({ timeout: 60000 });
  await page.getByRole("textbox", { name: /^dish$/i }).fill("Deep Pilau");
  await page.getByRole("textbox", { name: /^ingredient$/i }).fill("Rice");
  await page.getByRole("button", { name: /save recipe line/i }).click();
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: /^edit$/i }).first().click();
  await page.getByRole("textbox", { name: /^ingredient$/i }).fill("Basmati Rice");
  await page.getByRole("button", { name: /save recipe line/i }).click();
  await page.getByRole("button", { name: /^delete$/i }).first().click();
  await page.getByRole("textbox", { name: /^dish$/i }).fill("Deep Pilau");
  await page.getByRole("textbox", { name: /^ingredient$/i }).fill("Rice");
  await page.getByRole("button", { name: /save recipe line/i }).click();
  await page.getByRole("button", { name: /these recipes are in/i }).click();
  await shot(page, "05-recipes");
  const recipes = await (await apiGet(page.request, token!, "/api/v1/store/recipes")).json();
  expect((recipes.dishes || []).length).toBeGreaterThan(0);
  log("05-recipes", "add edit delete finish", "ok");

  // 4 Stock — opening count must go through the UI (Jack’s real flow)
  await page.goto("/store/stock", { waitUntil: "domcontentloaded" });
  await unlockPinIfNeeded(page, PIN);
  await expect(page.getByRole("heading", { name: /^opening count$/i })).toBeVisible({ timeout: 60_000 });
  const saveOpening = page.getByRole("button", { name: /save opening count/i });
  await expect(saveOpening).toBeVisible();
  await page.getByRole("textbox", { name: /^item$/i }).fill("Deep Rice");
  await page.getByRole("textbox", { name: /^quantity$/i }).fill("2");
  await page.getByRole("textbox", { name: /^unit$/i }).fill("kg");
  await page.getByRole("textbox", { name: /par level/i }).fill("20");
  await page.getByRole("textbox", { name: /reorder at/i }).fill("6");
  const yieldField = page.getByRole("textbox", { name: /yield/i });
  if (await yieldField.isVisible().catch(() => false)) await yieldField.fill("1");
  const sup = page.getByRole("combobox", { name: /default supplier/i });
  await expect(sup).toBeVisible({ timeout: 15_000 });
  await sup.selectOption({ index: 1 });
  const openingSave = page.waitForResponse(
    (r) => r.url().includes("/store/items/opening") && r.request().method() === "POST",
    { timeout: 30_000 },
  );
  await saveOpening.click();
  await openingSave;
  log("06-stock", "opening count ui", "ok");
  await shot(page, "06-stock");
  const items = await (await apiGet(page.request, token!, "/api/v1/store/items")).json();
  const deepRow = (items.items || []).find((i: { item_name: string }) => /deep rice/i.test(i.item_name));
  expect(deepRow, `items after stock: ${JSON.stringify(items.items || [])}`).toBeTruthy();
  expect((deepRow?.quantity ?? 0) as number).toBeGreaterThan(0);
  log("06-stock", "opening count", `qty=${deepRow?.quantity}`);

  // Day photos (open all zones)
  await page.goto("/store/day-photos", { waitUntil: "domcontentloaded" });
  await unlockPinIfNeeded(page, PIN);
  const zones = await (await apiGet(page.request, token!, "/api/v1/store/day-photos/status")).json();
  for (const zone of zones.zones || []) {
    if (zone.open_done) continue;
    await page.getByRole("combobox").selectOption({ label: zone.name });
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({ name: `zone-${zone.id}.jpg`, mimeType: "image/jpeg", buffer: JPEG });
    const savedZone = page.waitForResponse(
      (r) => r.url().includes("/day-photos") && r.request().method() === "POST" && r.status() >= 200 && r.status() < 300,
      { timeout: 45_000 },
    );
    await page.getByRole("button", { name: /save open photo/i }).click();
    await savedZone;
  }
  const zonesAfter = await (await apiGet(page.request, token!, "/api/v1/store/day-photos/status")).json();
  expect(zonesAfter.open_complete, `zones missing open: ${JSON.stringify(zonesAfter.zones)}`).toBeTruthy();
  await shot(page, "07-day-photos");

  // 5 Delivery
  await page.goto("/store/deliveries", { waitUntil: "domcontentloaded" });
  await unlockPinIfNeeded(page, PIN);
  await page.getByRole("combobox", { name: /^supplier$/i }).selectOption({ index: 1 });
  await page.getByRole("textbox", { name: /^item$/i }).fill("Deep Rice");
  await page.getByRole("textbox", { name: /^quantity$/i }).fill("2");
  await page.getByRole("textbox", { name: /^unit$/i }).fill("kg");
  const fileInputs = page.locator('input[type="file"][accept="image/*"]');
  await fileInputs.nth(0).setInputFiles({ name: "invoice.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await fileInputs.nth(1).setInputFiles({ name: "goods.jpg", mimeType: "image/jpeg", buffer: JPEG });
  const savedDelivery = page.waitForResponse(
    (r) => r.url().includes("/store/deliveries") && r.request().method() === "POST" && r.status() >= 200 && r.status() < 300,
    { timeout: 60000 },
  );
  await page.getByRole("button", { name: /receive delivery/i }).click();
  await savedDelivery;
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
  await unlockPinIfNeeded(page, PIN);
  await page.getByRole("textbox", { name: /^name$/i }).fill("Chef Deep");
  await page.getByRole("textbox", { name: /^pin$/i }).fill(CHEF_PIN);
  await page.getByRole("button", { name: /add chef/i }).click();
  await expect(page.getByText(/can confirm a handover/i)).toBeVisible({ timeout: 15000 });
  await page.goto("/store/issue", { waitUntil: "domcontentloaded" });
  await unlockPinIfNeeded(page, PIN);
  await page.getByRole("combobox", { name: /^item$/i }).selectOption("Deep Rice");
  await page.getByRole("textbox", { name: /^qty$/i }).fill("2");
  await page.getByRole("combobox", { name: /^chef$/i }).selectOption("Chef Deep");
  await page.getByLabel(/^chef pin/i).fill("0000");
  const issuePhoto = page.locator('input[type="file"]').first();
  await issuePhoto.setInputFiles({ name: "handover.jpg", mimeType: "image/jpeg", buffer: JPEG });
  const badHandover = page.waitForResponse(
    (r) => r.url().includes("/store/handover") && r.status() === 400,
    { timeout: 30000 },
  );
  await page.getByRole("button", { name: /hand it over/i }).click();
  await badHandover;
  await expect(page.getByText(/that pin is wrong/i)).toBeVisible({ timeout: 15000 });
  await shot(page, "09-handover-bad-pin");
  await page.getByLabel(/^chef pin/i).fill(CHEF_PIN);
  await page.getByRole("button", { name: /hand it over/i }).click();
  await expect(page.getByText(/handed to the kitchen/i)).toBeVisible({ timeout: 20000 });
  await shot(page, "10-handover-ok");

  // Waste
  await page.goto("/store/waste", { waitUntil: "domcontentloaded" });
  await unlockPinIfNeeded(page, PIN);
  await page.getByRole("combobox", { name: /^item$/i }).selectOption("Deep Rice");
  await page.getByRole("textbox", { name: /^quantity$/i }).fill("0.1");
  await page.getByRole("combobox", { name: /^second person$/i }).selectOption("Chef Deep");
  await page.getByRole("textbox", { name: /^their pin$/i }).fill(CHEF_PIN);
  await page.locator('input[type="file"]').first().setInputFiles({ name: "waste.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await page.getByRole("button", { name: /save waste/i }).click();
  await page.waitForTimeout(1000);
  await shot(page, "11-waste");

  // Restock — auto-draft after inventory touch (no test endpoints)
  let jackWaitingBefore = false;
  for (let attempt = 0; attempt < 45; attempt++) {
    const jackInbox = await (await apiGet(page.request, token!, "/api/v1/store/approval-inbox")).json();
    jackWaitingBefore = (jackInbox.pending || []).some((r: { approval_card_title?: string }) =>
      /waiting on/i.test(r.approval_card_title || ""),
    );
    if (jackWaitingBefore) {
      log("12-restock", "jack waiting (pre-owner)", jackInbox.pending?.[0]?.approval_card_title || "ok");
      break;
    }
    await page.waitForTimeout(1000);
  }
  const restockOrders = await (await apiGet(page.request, token!, "/api/v1/store/restock")).json();
  expect(
    (restockOrders.orders || []).some((o: { status?: string }) => o.status === "PENDING"),
    `expected PENDING PO, got ${JSON.stringify(restockOrders.orders || [])}`,
  ).toBeTruthy();
  expect(jackWaitingBefore, "Jack should see Waiting on after low-stock engine runs").toBeTruthy();
  await page.goto("/store/requests", { waitUntil: "domcontentloaded" });
  await unlockPinIfNeeded(page, PIN);
  await expect(page.getByText(/waiting on owner/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("main")).not.toBeEmpty();
  await shot(page, "12-restock-jack");

  if (OWNER_PASS || TEMP) {
    const ownerCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
    await ownerCtx.addInitScript(() => {
      sessionStorage.setItem("app_pin_unlocked", "1");
      sessionStorage.setItem("app_last_activity", String(Date.now()));
    });
    const ownerPage = await ownerCtx.newPage();
    await loginWithApi(ownerPage, OWNER, OWNER_PASS || TEMP);
    await ownerPage.goto("/eleven", { waitUntil: "domcontentloaded" });
    await expect(ownerPage.getByRole("heading", { name: /needs you/i })).toBeVisible({ timeout: 45000 });
    await shot(ownerPage, "13-owner-needs-you", { owner: true });
    await ownerPage.goto("/eleven/approvals", { waitUntil: "domcontentloaded" });
    const approve = ownerPage.getByRole("button", { name: /^approve$/i }).first();
    await expect(approve).toBeVisible({ timeout: 30_000 });
    const approveWait = ownerPage.waitForResponse(
      (r) => r.url().includes("/store/approvals") && r.request().method() === "POST",
      { timeout: 30_000 },
    );
    await approve.click();
    await approveWait;
    await ownerPage.goto("/eleven", { waitUntil: "domcontentloaded" });
    await expect(ownerPage.getByText(/nothing needs you right now/i)).toBeVisible({ timeout: 30_000 });
    await shot(ownerPage, "14-owner-after-approve", { owner: true });
    await ownerCtx.close();
    log("12-restock", "owner approved", "ok");
  }

  const probe = await (await page.request.get(`${API}/api/v1/test/storage-probe`)).json();
  expect(probe.round_trip_ok).toBe(true);
  expect(probe.backend).toBe("s3");
  log("storage", "probe", `backend=${probe.backend} host=${probe.endpoint_host || "n/a"}`);

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