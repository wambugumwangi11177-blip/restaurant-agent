/** Synthetic till evidence screenshots for CI (no live backend). */
import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const OUTPUT = path.resolve(__dirname, "../../docs/leviii/evidence");

async function installMocks(page: Page, state: "empty" | "failed" | "partial" | "error") {
  await page.route(/\/api\/v1\//, async (route) => {
    const url = new URL(route.request().url());
    const headers = {
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "*",
      "access-control-allow-methods": "GET,POST,OPTIONS",
    };
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (url.pathname.endsWith("/auth/me")) {
      return route.fulfill({
        headers,
        json: {
          id: 1,
          email: "synthetic@example.test",
          role: "admin",
          staff_role: "owner",
          tenant_name: "Eleven",
          restaurant_id: 1,
          restaurant_name: "Eleven",
          impersonation: null,
          is_email_verified: true,
          has_pin: false,
          must_change_password: false,
          password_auth_valid: true,
        },
      });
    }
    if (url.pathname.includes("/pos/quicksell/")) {
      if (state === "error" && url.pathname.endsWith("/status")) {
        return route.fulfill({ status: 503, headers, json: { detail: "Synthetic outage" } });
      }
      if (url.pathname.endsWith("/status")) {
        return route.fulfill({
          headers,
          json: {
            durable_inbox_enabled: true,
            source_bound: state !== "empty",
            receipts: state === "empty" ? 0 : 1,
            by_status: state === "empty" ? {} : { [state]: 1 },
            backlog: state === "empty" ? 0 : 1,
            last_receipt_at: state === "empty" ? null : "2026-11-09T10:00:00",
            last_successful_parse_at: null,
            completeness: "not_checked",
            sales_live: null,
            legacy_receipts: "not_counted_in_this_inbox",
            why: "Receipt and parsing are separate milestones.",
          },
        });
      }
      const rows =
        state === "empty"
          ? []
          : [
              {
                id: "synthetic-receipt-reference",
                received_at: "2026-11-09T10:00:00",
                status: state,
                attempts: 1,
                error_code: state === "failed" ? "mapping_failed" : null,
                parser_version: "synthetic-v1",
                parsed_at: null,
                last_attempt_at: "2026-11-09T10:00:00",
                payload_sha256: "synthetic-only",
              },
            ];
      return route.fulfill({ headers, json: rows });
    }
    return route.fulfill({ headers, json: { items: [], unread_count: 0 } });
  });
}

async function openTill(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "synthetic-review-session");
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
  await page.goto("/eleven/settings/till", { waitUntil: "networkidle" });
}

test("synthetic till evidence states", async ({ browser }) => {
  fs.mkdirSync(OUTPUT, { recursive: true });
  const checks: object[] = [];
  for (const width of [390, 1440]) {
    for (const state of ["empty", "failed", "partial", "error"] as const) {
      const context = await browser.newContext({ viewport: { width, height: 844 }, serviceWorkers: "block" });
      const page = await context.newPage();
      await installMocks(page, state);
      await openTill(page);
      await expect(page).not.toHaveURL(/\/login/);
      const snippet = (await page.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 240);
      test.info().attach(`body-${state}-${width}`, { body: snippet, contentType: "text/plain" });
      if (state === "error") {
        await expect(page.getByRole("main").getByRole("alert")).toBeVisible({ timeout: 45000 });
      } else {
        await expect(page.getByText("QuickSell receipt evidence")).toBeVisible({ timeout: 45000 });
      }
      const file = `pos-${state}-${width}.png`;
      await page.screenshot({ path: path.join(OUTPUT, file), fullPage: true });
      checks.push({ state, width, screenshot: file });
      await context.close();
    }
  }
  fs.writeFileSync(path.join(OUTPUT, "browser-results.json"), JSON.stringify({ syntheticOnly: true, checks }, null, 2) + "\n");
});