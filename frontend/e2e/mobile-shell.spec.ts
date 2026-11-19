import { test, expect } from "@playwright/test";
import path from "path";

const ARTIFACTS = process.env.CURSOR_ARTIFACTS || "/opt/cursor/artifacts";

const emptyFeed = {
  pending: [],
  events: [],
  cards: [],
  recipes_missing: 0,
  till_live: true,
};

const ownerMe = {
  id: 1,
  email: "owner@eleven.leviii",
  role: "admin",
  staff_role: "owner",
  tenant_name: "Eleven",
  restaurant_name: "Eleven",
  restaurant_id: 1,
  impersonation: null,
  is_email_verified: true,
  must_change_password: false,
  has_pin: true,
  password_auth_valid: true,
  display_name: "Wambugu",
  must_change_password: false,
};

const jackMe = {
  ...ownerMe,
  id: 2,
  email: "jack@eleven.leviii",
  role: "staff",
  staff_role: "stockkeeper",
  display_name: "Jack",
};

async function mockAuthed(page: import("@playwright/test").Page, me: typeof ownerMe) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/auth/me")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(me),
      });
      return;
    }
    if (url.includes("/store/approvals")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(emptyFeed),
      });
      return;
    }
    if (url.includes("/staff-setup")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          steps: [],
          app_unlocked: true,
          recipe_gap: null,
        }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

test.describe("mobile LEVIII shell", () => {
  test("login card stays opaque with reduced motion and frozen rAF", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.addInitScript(() => {
      window.requestAnimationFrame = () => 0;
    });
    await page.route("**/api/v1/**", async (route) => {
      if (route.request().url().includes("/auth/me")) {
        await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Unauthorized" }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.goto("/login");
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    const titleOpacity = await page.getByRole("heading", { level: 1 }).evaluate((el) => getComputedStyle(el).opacity);
    expect(Number(titleOpacity)).toBeGreaterThan(0.95);
    const buttonOpacity = await page.getByRole("button", { name: /sign in/i }).evaluate((el) => getComputedStyle(el).opacity);
    expect(Number(buttonOpacity)).toBeGreaterThan(0.95);
    await page.screenshot({ path: path.join(ARTIFACTS, "login-no-motion-fade.png"), fullPage: true });
  });

  test("set PIN and lock screens", async ({ page }) => {
    const needsPin = { ...ownerMe, has_pin: false };
    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/auth/me")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(needsPin) });
        return;
      }
      if (url.includes("/auth/pin/set")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "pin_set" }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "playwright-pin-token");
    });
    await page.goto("/eleven");
    await expect(page.getByText(/Choose a PIN/i)).toBeVisible();
    await page.screenshot({ path: path.join(ARTIFACTS, "pin-set-mobile.png"), fullPage: true });

    const locked = { ...ownerMe };
    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/auth/me")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(locked) });
        return;
      }
      if (url.includes("/auth/pin/unlock")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "unlocked", display_name: "Wambugu" }),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(emptyFeed) });
    });
    await page.goto("/eleven");
    await expect(page.getByText(/Enter your 4-digit PIN/i)).toBeVisible();
    await page.screenshot({ path: path.join(ARTIFACTS, "pin-lock-mobile.png"), fullPage: true });
  });

  test("login layout with short viewport (keyboard)", async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      if (route.request().url().includes("/auth/me")) {
        await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Unauthorized" }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto("/login");
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    await page.screenshot({ path: path.join(ARTIFACTS, "login-mobile-740.png"), fullPage: true });

    await page.setViewportSize({ width: 360, height: 400 });
    await page.goto("/login");
    const submit = page.getByRole("button", { name: /sign in/i });
    await expect(submit).toBeVisible();
    await submit.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(ARTIFACTS, "login-keyboard-400.png"), fullPage: true });
  });

  test("owner home after session", async ({ page }) => {
    await mockAuthed(page, ownerMe);
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "playwright-owner-token");
      sessionStorage.setItem("app_pin_unlocked", "1");
      sessionStorage.setItem("app_last_activity", String(Date.now()));
    });
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto("/eleven");
    await expect(page.getByRole("heading", { name: "Needs you" })).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "owner-home-mobile.png"), fullPage: true });
  });

  test("store home after session", async ({ page }) => {
    await mockAuthed(page, jackMe);
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "playwright-jack-token");
      sessionStorage.setItem("app_pin_unlocked", "1");
      sessionStorage.setItem("app_last_activity", String(Date.now()));
    });
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto("/store");
    await expect(page.getByText(/How a delivery is kept/i)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "store-home-mobile.png"), fullPage: true });
  });
});