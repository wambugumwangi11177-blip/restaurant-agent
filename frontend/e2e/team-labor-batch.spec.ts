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
  display_name: "Owner",
};

const jackMe = { ...ownerMe, id: 2, email: "jack@eleven.leviii", role: "staff", staff_role: "stockkeeper", display_name: "Jack" };

const accountantMe = {
  ...ownerMe,
  id: 3,
  email: "acc@eleven.leviii",
  role: "staff",
  staff_role: "controller",
  display_name: "Accountant",
};

const teamOverview = {
  today: "2026-01-01",
  week_start: "2025-12-29",
  on_shift_now: [{ staff_member_id: 1, name: "Joy", role_title: "waiter", window: "09:00–17:00" }],
  week_schedule: [
    {
      staff_member_id: 1,
      name: "Joy",
      role_title: "waiter",
      weekly_hours: 32,
      compact_lines: ["Mon–Thu 09:00–17:00"],
    },
  ],
  overwork_warnings: [],
  labour_cost_today_cents: 150000,
  shift_sales_status: "coming",
  rules: { alerts_enabled: true, max_hours_per_week: 52, max_consecutive_days: 6 },
};

async function mockOwner(page: import("@playwright/test").Page) {
  await page.route(/\/api\/v1\//, async (route) => {
    const url = route.request().url();
    if (url.includes("/auth/me")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ownerMe) });
      return;
    }
    if (url.includes("/team/overview")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(teamOverview) });
      return;
    }
    if (url.includes("/team/rules")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ alerts_enabled: true, max_hours_per_week: 52, max_consecutive_days: 6 }),
      });
      return;
    }
    if (url.includes("/team/roster")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ id: 1, name: "Joy", role_title: "waiter" }]) });
      return;
    }
    if (url.includes("/team/weekly-slots")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          slots: [
            { staff_member_id: 1, weekday: 0, start_time: "09:00", end_time: "17:00" },
            { staff_member_id: 1, weekday: 1, start_time: "09:00", end_time: "17:00" },
            { staff_member_id: 1, weekday: 2, start_time: "09:00", end_time: "17:00" },
            { staff_member_id: 1, weekday: 3, start_time: "09:00", end_time: "17:00" },
          ],
          roster: [{ id: 1, name: "Joy", role_title: "waiter" }],
          members: [
            {
              staff_member_id: 1,
              name: "Joy",
              role_title: "waiter",
              compact_lines: ["Mon–Thu 09:00–17:00"],
              weekly_hours: 32,
              weekdays: [0, 1, 2, 3],
            },
          ],
          today_weekday: 0,
          scheduled_today_ids: [1],
          today: "2026-01-01",
          timezone: "Africa/Nairobi",
        }),
      });
      return;
    }
    if (url.includes("/store/approvals")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...emptyFeed,
          pending: [
            {
              id: 1,
              kind: "waste",
              status: "needs_approval",
              item_name: "Tomatoes",
              quantity: 3,
              unit: "kg",
              reason_text: "Spoiled",
              person_name: "Jack",
              created_at: "2026-11-23T10:00:00",
              approval_card_title: "Write-off",
              approval_needs_you: true,
              approval_reason_line: "Spoiled",
              approval_when_label: "Today 10:00",
              approval_detail_bullets: ["Tomatoes — 3 kg", "Asked by Jack", "Today 10:00"],
              approval_viewer_is_actor: true,
            },
          ],
        }),
      });
      return;
    }
    if (url.includes("/staff-setup")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ people: [], entries: [] }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

test.describe("team labor batch screenshots", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
  });

  test("capture team labor screens", async ({ page }) => {
    await mockOwner(page);
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "team-batch");
      sessionStorage.setItem("app_pin_unlocked", "1");
      sessionStorage.setItem("app_last_activity", String(Date.now()));
    });

    await page.goto("/eleven");
    await expect(page.getByText(/Needs you|Activity|Eleven/i).first()).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "owner-home-390.png") });

    await page.goto("/eleven/team");
    await expect(page.getByRole("heading", { name: "On shift now" })).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "team-tab-390.png") });

    await page.goto("/eleven/settings/team-rules");
    await expect(page.getByText(/Max hours per week/i)).toBeVisible();
    await page.screenshot({ path: path.join(ARTIFACTS, "team-rules-390.png") });

    await page.goto("/eleven/schedule");
    await expect(page.getByText(/Save schedule/i)).toBeVisible();
    await page.screenshot({ path: path.join(ARTIFACTS, "manager-schedule-390.png") });

    await page.goto("/eleven/approvals");
    await expect(page.getByText("Write-off")).toBeVisible();
    await page.screenshot({ path: path.join(ARTIFACTS, "approvals-card-390.png") });

    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/auth/me")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(jackMe) });
        return;
      }
      if (url.includes("/team/weekly-slots")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            slots: [{ staff_member_id: 1, weekday: 0, start_time: "09:00", end_time: "17:00" }],
            roster: [{ id: 1, name: "Joy", role_title: "waiter" }],
            members: [
              {
                staff_member_id: 1,
                name: "Joy",
                role_title: "waiter",
                compact_lines: ["Mon 09:00–17:00"],
                weekly_hours: 8,
                weekdays: [0],
              },
            ],
            today_weekday: 0,
            scheduled_today_ids: [1],
            today: "2026-01-01",
          }),
        });
        return;
      }
      if (url.includes("/approval-inbox")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            pending: [
              {
                id: 2,
                kind: "waste",
                approval_card_title: "Waiting on Owner",
                approval_card_subtitle: "Write-off",
                approval_type_label: "Write-off",
                approval_viewer_is_actor: false,
              },
            ],
          }),
        });
        return;
      }
      if (url.includes("/my-requests")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) });
        return;
      }
      if (url.includes("/staff-setup")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ steps: [], app_unlocked: true, recipe_gap: null }),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.goto("/store");
    await expect(page.getByText(/delivery|Today/i).first()).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "jack-store-home-390.png") });

    await page.goto("/store/schedule");
    await expect(page.getByText(/Save schedule/i)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "manager-schedule-jack-390.png") });

    await page.goto("/store/requests");
    await expect(page.getByText("Waiting on Owner")).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "waiting-on-owner-390.png") });

    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/auth/me")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(accountantMe) });
        return;
      }
      if (url.includes("/store/deliveries") && !url.includes("/photos")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: 9,
              supplier: "Fresh Farm",
              lines: [{ id: 1, item_name: "Rice", quantity: 8, unit: "kg" }],
              photos: [{ id: 1, kind: "invoice" }],
            },
          ]),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.goto("/store/invoice-prices");
    await expect(page.getByText(/Confirm prices/i)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: path.join(ARTIFACTS, "accountant-price-confirm-390.png") });

    await mockOwner(page);
    await page.goto("/eleven/staff");
    await expect(page.getByText("Dashboard login")).toBeVisible();
    await expect(page.locator('select').first().locator('option')).toHaveCount(3);
    await page.screenshot({ path: path.join(ARTIFACTS, "staff-create-no-waiter-login-390.png") });
  });
});