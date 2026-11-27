const { chromium } = require("playwright");
const base = process.env.POS_REVIEW_BASE_URL || "http://127.0.0.1:3000";

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on("request", (req) => {
    if (req.url().includes("/api/v1/")) console.log("req", req.url());
  });
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "tok");
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
  await page.route(/\/api\/v1\//, async (route) => {
    const url = new URL(route.request().url());
    const h = { "access-control-allow-origin": "*" };
    if (url.pathname.endsWith("/auth/me")) {
      return route.fulfill({
        headers: h,
        json: {
          id: 1,
          email: "s@t",
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
    if (url.pathname.includes("/pos/quicksell/status")) {
      return route.fulfill({
        headers: h,
        json: {
          durable_inbox_enabled: true,
          source_bound: true,
          receipts: 0,
          backlog: 0,
          last_receipt_at: null,
          last_successful_parse_at: null,
          completeness: "not_checked",
          sales_live: null,
          legacy_receipts: "not_counted_in_this_inbox",
          why: "test",
        },
      });
    }
    if (url.pathname.includes("/pos/quicksell/")) {
      return route.fulfill({ headers: h, json: [] });
    }
    return route.fulfill({ headers: h, json: { items: [], unread_count: 0 } });
  });
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    sessionStorage.setItem("access_token", "tok");
    sessionStorage.setItem("app_pin_unlocked", "1");
    sessionStorage.setItem("app_last_activity", String(Date.now()));
  });
  const me = page.waitForResponse((r) => r.url().includes("/auth/me"), { timeout: 20000 });
  await page.goto(`${base}/eleven/settings/till`, { waitUntil: "domcontentloaded", timeout: 60000 });
  try {
    await me;
  } catch (e) {
    console.log("no auth/me response");
  }
  console.log("url", page.url());
  await page.waitForTimeout(4000);
  console.log("h2", await page.locator("h2").allTextContents());
  console.log(await page.locator("body").innerText().catch(() => "no text"));
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});