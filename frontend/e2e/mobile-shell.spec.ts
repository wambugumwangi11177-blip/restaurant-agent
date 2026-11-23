import { test, expect } from "@playwright/test";
import path from "path";

const ARTIFACTS = process.env.CURSOR_ARTIFACTS || "/opt/cursor/artifacts";

const emptyFeed = {
  pending: [],
  events: [],
  cards: [],
  recipes_missing: 0,
  till_live: true,
  attention: { count: 0, sentence: "Nothing needs you right now." },
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

  test("logged-in LEVIIIStore /login does not leave login #password over glass", async ({ browser }) => {
    const context = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 LEVIIIStore/1.0.8",
      viewport: { width: 412, height: 915 },
    });
    const page = await context.newPage();
    await mockAuthed(page, ownerMe);
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "playwright-logged-in");
      document.documentElement.dataset.leviiiApk = "true";
    });
    await page.goto("/login");
    await page.waitForURL(/\/eleven/, { timeout: 15_000 });
    await expect(page.locator("#password")).toHaveCount(0);
    await expect(page.getByText(/Enter your 4-digit PIN/i)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "logged-in-login-handoff-lock.png"), fullPage: true });
    await context.close();
  });

  test("logged-in Jack on root lands on visible store or lock", async ({ browser }) => {
    const context = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 LEVIIIStore/1.0.8",
      viewport: { width: 412, height: 915 },
    });
    const page = await context.newPage();
    await mockAuthed(page, jackMe);
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "playwright-jack");
      document.documentElement.dataset.leviiiApk = "true";
    });
    await page.goto("/");
    await page.waitForURL(/\/store/, { timeout: 15_000 });
    await expect(page.locator("#password")).toHaveCount(0);
    await expect(
      page.getByText(/Enter your 4-digit PIN/i).or(page.getByText(/How a delivery is kept/i)),
    ).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "logged-in-jack-first-screen.png"), fullPage: true });
    await context.close();
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

const setupPayload = {
  must_change_password: false,
  has_pin: true,
  app_unlocked: true,
  unlocked_modules: ["opening-count", "stock"],
  steps: [
    { id: "account", title: "Account", state: "done", unlocks: "recipes", locked_reason: null, completed_at: null },
    { id: "recipes", title: "Recipes", state: "done", unlocks: "questionnaire", locked_reason: null, completed_at: null },
    { id: "questionnaire", title: "Questions", state: "done", unlocks: "stock", locked_reason: null, completed_at: null },
    { id: "stock", title: "Stock", state: "done", unlocks: "app", locked_reason: null, completed_at: null },
  ],
  recipe_gap: { dish_count: 0, missing_count: 0, missing_names: [] },
};

async function mockThemeOwnerApis(page: import("@playwright/test").Page, feed: typeof emptyFeed = emptyFeed) {
  await mockAuthed(page, ownerMe);
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/auth/me")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ownerMe) });
      return;
    }
    if (url.includes("/store/approvals")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(feed),
      });
      return;
    }
    if (url.includes("/staff-setup")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          people: [
            {
              user_id: 2,
              email: "jack@eleven.leviii",
              name: "Jack",
              staff_role: "stockkeeper",
              account: "done",
              recipes: "done",
              questionnaire: "done",
              app_unlocked: true,
            },
          ],
          entries: [],
          recipe_gap: { missing_count: 0 },
        }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

async function mockThemeJackApis(page: import("@playwright/test").Page) {
  await mockAuthed(page, jackMe);
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/auth/me")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(jackMe) });
      return;
    }
    if (url.includes("/staff-setup")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(setupPayload) });
      return;
    }
    if (url.includes("/store/items")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{ id: 1, item_name: "Tomatoes", quantity: 12, unit: "kg", buying_unit: "crate", units_per_buy: 20, yield_fraction: 1, zone: "Main store" }],
          zones: [{ name: "Main store" }],
        }),
      });
      return;
    }
    if (url.includes("/store/approvals")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(emptyFeed) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

test.describe("warm earthy theme screenshots", () => {
  test("390px palette verification", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    await page.route("**/api/v1/**", async (route) => {
      if (route.request().url().includes("/auth/me")) {
        await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Unauthorized" }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.goto("/login");
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    await page.screenshot({ path: path.join(ARTIFACTS, "theme-login-390.png") });

    await mockThemeOwnerApis(page);
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "theme-owner");
      sessionStorage.setItem("app_pin_unlocked", "1");
      sessionStorage.setItem("app_last_activity", String(Date.now()));
    });

    await page.goto("/eleven");
    await expect(page.getByRole("heading", { name: "Needs you" })).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "theme-owner-home-390.png") });

    const approvalsFeed = {
      ...emptyFeed,
      attention: { count: 1, sentence: "1 thing needs you." },
      pending: [
        {
          id: 1,
          kind: "delivery",
          action: "Approve supplier delivery",
          headline: "Tomatoes delivery",
          created_at: new Date().toISOString(),
        },
      ],
    };
    await mockThemeOwnerApis(page, approvalsFeed);
    await page.goto("/eleven/approvals");
    await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "theme-approvals-390.png") });

    await page.goto("/eleven/staff");
    await expect(page.getByRole("heading", { name: "Staff" })).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "theme-staff-390.png") });

    await mockThemeJackApis(page);
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "theme-jack");
    });
    await page.goto("/store");
    await expect(page.getByText(/How a delivery is kept/i)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "theme-jack-home-390.png") });

    await page.goto("/store/stock");
    await expect(page.getByText(/Quantities only/i)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "theme-stock-390.png") });
  });
});