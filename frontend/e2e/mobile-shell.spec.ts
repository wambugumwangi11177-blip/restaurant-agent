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
  has_pin: false,
};

const jackMe = {
  ...ownerMe,
  id: 2,
  email: "jack@eleven.leviii",
  role: "staff",
  staff_role: "stockkeeper",
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
    });
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto("/store");
    await expect(page.getByText(/How a delivery is kept/i)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "store-home-mobile.png"), fullPage: true });
  });
});