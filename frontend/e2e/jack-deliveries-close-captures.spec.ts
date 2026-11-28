import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const OUT = process.env.SHOT_DIR || "/cursor/stores/self/artifacts";
const API = process.env.NEXT_PUBLIC_API_URL || "https://backend-test-production-05524237.up.railway.app";
const JACK = "jack@eleven.leviii";
const CONTROLLER = "amina@eleven.leviii";
const TEMP = process.env.SEED_STAFF_PASSWORD || "";
const MIN_STD = 8;

const JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAgP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=",
  "base64",
);

function pngStddev(file: string): number {
  return Number(
    execFileSync("python3", ["-c", "from PIL import Image; import numpy as np, sys; a=np.array(Image.open(sys.argv[1]).convert('RGB')); print(float(a.std()))", file], {
      encoding: "utf8",
    }).trim(),
  );
}

async function waitStore(page: Page) {
  await expect(page.getByRole("navigation", { name: /store/i })).toBeVisible({ timeout: 45_000 });
  await page.waitForFunction(() => (document.querySelector("main")?.textContent?.trim().length ?? 0) > 20, { timeout: 45_000 });
}

async function shot(page: Page, name: string) {
  await waitStore(page);
  const file = path.join(OUT, `jack-dc-${name}.png`);
  await page.screenshot({ path: file, fullPage: true, animations: "disabled" });
  expect(pngStddev(file)).toBeGreaterThan(MIN_STD);
}

async function login(page: Page, email: string, pass: string) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem("app_pin_unlocked", "1");
    window.sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(pass);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 90_000 });
}

test("jack deliveries close captures", async ({ page }) => {
  test.setTimeout(420_000);
  test.skip(!TEMP, "SEED_STAFF_PASSWORD required");
  fs.mkdirSync(OUT, { recursive: true });
  await login(page, JACK, TEMP);

  await page.goto("/store/deliveries", { waitUntil: "domcontentloaded" });
  await page.getByRole("combobox", { name: /supplier/i }).selectOption({ index: 1 });
  await page.getByRole("button", { name: /add another line/i }).click();
  const fileInputs = page.locator('input[type="file"][accept="image/*"]');
  await fileInputs.nth(0).setInputFiles({ name: "inv.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await fileInputs.nth(1).setInputFiles({ name: "goods.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await shot(page, "01-deliveries-form");

  await page.goto("/store/close", { waitUntil: "domcontentloaded" });
  await shot(page, "02-stock-close");

  await page.goto("/store/requests", { waitUntil: "domcontentloaded" });
  await shot(page, "03-jack-requests");

  await page.evaluate(() => window.sessionStorage.clear());
  await login(page, CONTROLLER, TEMP);
  await page.goto("/store/cash-close", { waitUntil: "domcontentloaded" });
  await shot(page, "04-cash-close");

  const inbox = await page.request.get(`${API}/api/v1/store/approval-inbox`, {
    headers: { Authorization: `Bearer ${await page.evaluate(() => sessionStorage.getItem("access_token"))}` },
  });
  expect(inbox.ok()).toBeTruthy();
});