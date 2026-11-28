import { test, expect, devices, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const API = process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app";
const FRONT = process.env.LIVE_FRONTEND || "https://frontend-test-production-752b1b7c.up.railway.app";
const STAFF_PASS = process.env.SEED_STAFF_PASSWORD || "";
const OWNER_PASS = process.env.SEED_OWNER_PASSWORD || "";
const OUT = process.env.SHOT_DIR || "/workspace/jack-dc-shots";
const MONEY_KEYS = new Set([
  "cost_per_unit", "cost_per_unit_cents", "cost_price", "total_cost", "value_cents", "price", "unit_price", "total",
  "hourly_rate", "revenue", "profit", "pnl", "amount_cents", "sale_price", "subtotal", "monthly_impact_cents",
  "suggested_price", "current_price", "total_cents", "old_price", "new_price",
]);
const MONEY_TEXT = /\b(KES|KSh|Ksh)\b|\bSh\.?\s?\d|\$\s?\d/;
const JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAgP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=",
  "base64",
);
const photo = (name: string) => ({ name, mimeType: "image/jpeg", buffer: JPEG });

function moneyKeysIn(value: unknown, trail = ""): string[] {
  if (Array.isArray(value)) return value.flatMap((item, i) => moneyKeysIn(item, `${trail}[${i}]`));
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, item]) => [
      ...(MONEY_KEYS.has(key) ? [`${trail}.${key}`] : []),
      ...moneyKeysIn(item, `${trail}.${key}`),
    ]);
  }
  return [];
}

function pngStddev(file: string): number {
  return Number(
    execFileSync("python3", ["-c", "from PIL import Image; import numpy as np, sys; print(float(np.array(Image.open(sys.argv[1]).convert('RGB')).std()))", file], { encoding: "utf8" }).trim(),
  );
}

function nairobiHHMM(minutesAgo: number): string {
  const d = new Date(Date.now() + 3 * 3600_000 - minutesAgo * 60_000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

async function token(request: APIRequestContext, email: string, password: string): Promise<string> {
  const res = await request.post(`${API}/api/v1/auth/login`, { data: { email, password } });
  expect(res.ok(), `login ${email}`).toBeTruthy();
  return (await res.json()).access_token;
}

const auth = (tok: string) => ({ Authorization: `Bearer ${tok}` });

async function session(browser: Browser, tok: string): Promise<Page> {
  const context = await browser.newContext({ ...devices["Pixel 5"], viewport: { width: 360, height: 740 }, baseURL: FRONT });
  await context.addInitScript((t) => {
    window.sessionStorage.setItem("access_token", t);
    window.sessionStorage.setItem("app_pin_unlocked", "1");
    window.sessionStorage.setItem("app_last_activity", String(Date.now()));
  }, tok);
  return context.newPage();
}

async function settle(page: Page, marker?: RegExp) {
  await page.waitForFunction(() => (document.querySelector("main")?.textContent?.trim().length ?? 0) > 20, { timeout: 45_000 });
  if (marker) await expect(page.locator("main")).toContainText(marker, { timeout: 45_000 });
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(OUT, { recursive: true });
  const file = path.join(OUT, `jack-dc-${name}.png`);
  await page.screenshot({ path: file, fullPage: true, animations: "disabled" });
  expect(pngStddev(file), `${name} is not blank`).toBeGreaterThan(8);
}

type Item = { id: number; item_name: string; quantity: number; unit: string; balances: unknown[] };
async function items(request: APIRequestContext, tok: string): Promise<Item[]> {
  const res = await request.get(`${API}/api/v1/store/items`, { headers: auth(tok) });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).items;
}

test.describe.configure({ mode: "serial" });
test.skip(!STAFF_PASS || !OWNER_PASS, "SEED_STAFF_PASSWORD and SEED_OWNER_PASSWORD required");

let jackToken = "";
let aminaToken = "";
let ownerToken = "";

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext();
  jackToken = await token(request, "jack@eleven.leviii", STAFF_PASS);
  aminaToken = await token(request, "amina@eleven.leviii", STAFF_PASS);
  ownerToken = await token(request, "owner@eleven.leviii", OWNER_PASS);
  await request.dispose();
});

test("multi-line delivery with photos raises stock per line and locks units", async ({ browser, request }) => {
  const status = await (await request.get(`${API}/api/v1/store/day-photos/status`, { headers: auth(jackToken) })).json();
  for (const zone of status.zones.filter((z: { open_done: boolean }) => !z.open_done)) {
    const res = await request.post(`${API}/api/v1/store/day-photos`, {
      headers: auth(jackToken),
      multipart: { zone_id: String(zone.id), phase: "open", photo: photo("zone.jpg") },
    });
    expect(res.status()).toBe(201);
  }
  const before = await items(request, jackToken);
  const stocked = before.find((i) => i.unit === "kg" && i.balances.length > 0)!;
  expect(stocked, "a kg item that already has zone balances").toBeTruthy();
  const newName = `DC Eggs ${Date.now()}`;

  const page = await session(browser, jackToken);
  await page.goto("/store/deliveries", { waitUntil: "domcontentloaded" });
  const supplier = page.getByRole("combobox", { name: /supplier/i });
  await expect(supplier.locator("option")).not.toHaveCount(1, { timeout: 45_000 });
  await supplier.selectOption({ index: 1 });
  await page.getByRole("combobox", { name: "item" }).first().selectOption(String(stocked.id));
  await expect(page.getByLabel("Unit (from stock)")).toHaveValue(stocked.unit);
  await page.getByLabel("quantity").first().fill("2.5");
  await page.getByRole("button", { name: /add another line/i }).click();
  await page.getByRole("button", { name: "New item" }).nth(1).click();
  await page.getByLabel("item", { exact: true }).nth(1).fill(newName);
  await page.locator("select").nth(2).selectOption("pcs");
  await page.getByLabel("quantity").nth(1).fill("30");
  const files = page.locator('input[type="file"][accept="image/*"]');
  await files.nth(0).setInputFiles(photo("invoice.jpg"));
  await files.nth(1).setInputFiles(photo("goods.jpg"));
  await shot(page, "10-delivery-two-lines-filled");
  await page.getByRole("button", { name: /receive delivery/i }).click();
  await expect(page.locator("main")).toContainText(newName, { timeout: 60_000 });
  await shot(page, "11-delivery-saved");

  const after = await items(request, jackToken);
  const stockedAfter = after.find((i) => i.id === stocked.id)!;
  expect(stockedAfter.quantity).toBeCloseTo(stocked.quantity + 2.5, 5);
  expect(stockedAfter.unit).toBe(stocked.unit);
  const eggs = after.find((i) => i.item_name === newName)!;
  expect(eggs.quantity).toBe(30);
  expect(eggs.unit).toBe("pcs");

  const list = await (await request.get(`${API}/api/v1/store/deliveries`, { headers: auth(jackToken) })).json();
  expect(list[0].lines.map((l: { unit: string }) => l.unit)).toEqual([stocked.unit, "pcs"]);
  expect(moneyKeysIn(list)).toEqual([]);

  const wrongUnit = await request.post(`${API}/api/v1/store/deliveries`, {
    headers: auth(jackToken),
    multipart: {
      supplier_id: String(list[0].supplier_id ?? (await (await request.get(`${API}/api/v1/store/suppliers`, { headers: auth(jackToken) })).json())[0].id),
      lines: JSON.stringify([{ item_id: stocked.id, quantity: 1, unit: "g" }]),
      invoice: photo("invoice.jpg"),
      goods: photo("goods.jpg"),
    },
  });
  expect(wrongUnit.status()).toBe(201);
  expect((await wrongUnit.json()).lines[0].unit).toBe(stocked.unit);
  const badUnit = await request.post(`${API}/api/v1/store/deliveries`, {
    headers: auth(jackToken),
    multipart: {
      supplier_id: String(list[0].supplier_id ?? (await (await request.get(`${API}/api/v1/store/suppliers`, { headers: auth(jackToken) })).json())[0].id),
      lines: JSON.stringify([{ item_name: "DC Bad", quantity: 1, unit: "furlong" }]),
      invoice: photo("invoice.jpg"),
      goods: photo("goods.jpg"),
    },
  });
  expect(badUnit.status()).toBe(400);
  await page.context().close();
});

test("Jack cannot open cash close and sees no money", async ({ browser, request }) => {
  const page = await session(browser, jackToken);
  for (const route of ["/store", "/store/deliveries", "/store/stock", "/store/close", "/store/requests", "/store/costs"]) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    await settle(page);
    await page.waitForTimeout(1500);
    expect(await page.locator("body").innerText(), `money text on ${route}`).not.toMatch(MONEY_TEXT);
  }
  await page.goto("/store/cash-close", { waitUntil: "domcontentloaded" });
  await settle(page, /Not your screen/);
  await expect(page.locator("main input, main textarea")).toHaveCount(0);
  expect(await page.locator("body").innerText()).not.toMatch(MONEY_TEXT);
  await shot(page, "12-jack-cash-close-blocked");

  expect((await request.get(`${API}/api/v1/store/cash-close/status`, { headers: auth(jackToken) })).status()).toBe(403);
  const post = await request.post(`${API}/api/v1/store/cash-close`, {
    headers: auth(jackToken),
    data: { cash_counted_kes: 1, mpesa_counted_kes: 1 },
  });
  expect(post.status()).toBe(403);
  for (const route of ["items", "deliveries", "approval-inbox", "my-requests"]) {
    const res = await request.get(`${API}/api/v1/store/${route}`, { headers: auth(jackToken) });
    expect(moneyKeysIn(await res.json()), `money keys in ${route}`).toEqual([]);
  }
  await page.context().close();
});

test("close reminder reaches the bell and Needs you / Waiting on, repeats at +30m, then restores 22:00", async ({ browser, request }) => {
  test.skip(new Date(Date.now() + 3 * 3600_000).getUTCHours() < 1, "needs to be at least 61 minutes into the Nairobi day");
  const fire = async (minutesAgo: number) => {
    const res = await request.post(`${API}/api/v1/test/day-close-reminders`, {
      headers: auth(ownerToken),
      data: { reminder_time: nairobiHHMM(minutesAgo) },
    });
    expect(res.ok()).toBeTruthy();
    return (await res.json()).sent as number;
  };
  const feed = async (tok: string) =>
    (await (await request.get(`${API}/api/v1/notifications/`, { headers: auth(tok), params: { limit: 50 } })).json()).items as { title: string; body: string }[];
  try {
    await fire(1);
    const jackFeed = await feed(jackToken);
    expect(jackFeed.some((n) => n.title === "Close the day — stock" && n.body.endsWith(":0]"))).toBeTruthy();
    expect((await feed(aminaToken)).some((n) => n.title === "Close the day — cash")).toBeTruthy();

    const jack = await session(browser, jackToken);
    await jack.goto("/store", { waitUntil: "domcontentloaded" });
    await settle(jack);
    await jack.getByRole("button", { name: "Notifications" }).first().click();
    await expect(jack.getByText("Close the day — stock").first()).toBeVisible({ timeout: 30_000 });
    await shot(jack, "20-jack-bell-close-reminder");
    await jack.goto("/store/requests", { waitUntil: "domcontentloaded" });
    await settle(jack, /Count stock and close the day/);
    await expect(jack.locator("main")).toContainText(/Waiting on Accountant/);
    await shot(jack, "21-jack-needs-you-waiting-on");
    await jack.context().close();

    const amina = await session(browser, aminaToken);
    await amina.goto("/store", { waitUntil: "domcontentloaded" });
    await settle(amina);
    await amina.getByRole("button", { name: "Notifications" }).first().click();
    await expect(amina.getByText("Close the day — cash").first()).toBeVisible({ timeout: 30_000 });
    await shot(amina, "22-accountant-bell-close-reminder");
    await amina.goto("/store/requests", { waitUntil: "domcontentloaded" });
    await settle(amina, /Record cash and M-Pesa for today/);
    await shot(amina, "23-accountant-needs-you");
    await amina.context().close();

    const owner = await session(browser, ownerToken);
    await owner.goto("/eleven", { waitUntil: "domcontentloaded" });
    await expect(owner.getByText(/Waiting on/i).first()).toBeVisible({ timeout: 45_000 });
    await shot(owner, "24-owner-waiting-on-store");
    await owner.context().close();

    await fire(31);
    expect((await feed(jackToken)).some((n) => n.title === "Close the day — stock" && n.body.endsWith(":30]"))).toBeTruthy();
    expect(await fire(31)).toBe(0);
  } finally {
    await request.post(`${API}/api/v1/test/day-close-reminders`, { headers: auth(ownerToken), data: { reminder_time: "22:00" } });
  }
  const status = await (await request.get(`${API}/api/v1/store/cash-close/status`, { headers: auth(aminaToken) })).json();
  expect(status.reminder_time).toBe("22:00");
});

test("accountant submits the cash close", async ({ browser, request }) => {
  const before = await (await request.get(`${API}/api/v1/store/cash-close/status`, { headers: auth(aminaToken) })).json();
  test.skip(before.cash_closed, "today's cash is already closed on this stack");
  const page = await session(browser, aminaToken);
  await page.goto("/store/cash-close", { waitUntil: "domcontentloaded" });
  await settle(page, /Cash counted/);
  await page.getByLabel(/Cash counted/).fill("12500");
  await page.getByLabel(/M-Pesa counted/).fill("8300");
  await shot(page, "30-cash-close-filled");
  await page.getByRole("button", { name: /save cash close/i }).click();
  await expect(page.locator("main")).toContainText(/recorded/i, { timeout: 30_000 });
  await shot(page, "31-cash-close-saved");
  const after = await (await request.get(`${API}/api/v1/store/cash-close/status`, { headers: auth(aminaToken) })).json();
  expect(after.cash_closed).toBe(true);
  expect(after.cash_counted_kes).toBe(12500);
  expect(after.mpesa_counted_kes).toBe(8300);
  const again = await request.post(`${API}/api/v1/store/cash-close`, {
    headers: auth(aminaToken),
    data: { cash_counted_kes: 1, mpesa_counted_kes: 1 },
  });
  expect(again.status()).toBe(409);
  const ownerFeed = (await (await request.get(`${API}/api/v1/notifications/`, { headers: auth(ownerToken), params: { limit: 50 } })).json()).items as { title: string }[];
  expect(ownerFeed.some((n) => n.title === "Cash close recorded")).toBeTruthy();
  await page.context().close();
});
