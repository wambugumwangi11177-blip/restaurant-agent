/* Isolated browser review. All API responses are synthetic, never production. */
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(require.resolve("playwright", {
  paths: [process.cwd(), process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES || process.cwd()],
}));

async function main() {
  const base = process.env.POS_REVIEW_BASE_URL || "http://127.0.0.1:3000";
  if (!["localhost", "127.0.0.1"].includes(new URL(base).hostname)) {
    throw new Error("Browser review only permits a local synthetic frontend");
  }
  const output = path.resolve(__dirname, "../../docs/leviii/evidence");
  await fs.mkdir(output, { recursive: true });
  let available = false;
  for (let attempt = 0; attempt < 30; attempt++) {
    try { if ((await fetch(base)).ok) { available = true; break; } } catch { /* local server starting */ }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  if (!available) throw new Error("Local review frontend did not start");
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, headless: true });
  const checks = [];
  try {
    for (const width of [390, 1440]) {
      for (const state of ["empty", "failed", "error"]) {
        const page = await browser.newPage({ viewport: { width, height: 844 } });
        await page.addInitScript(() => sessionStorage.setItem("access_token", "synthetic-review-session"));
        await page.route("**/api/v1/**", async route => {
          const url = new URL(route.request().url());
          const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,OPTIONS" };
          if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
          let data;
          if (url.pathname.endsWith("/auth/me")) {
            data = { id: 1, email: "synthetic@example.test", role: "admin", staff_role: "owner", tenant_name: "Eleven", impersonation: null, is_email_verified: false };
          } else if (url.pathname.includes("/pos/quicksell/")) {
            if (state === "error") return route.fulfill({ status: 503, headers, json: { detail: "Synthetic outage" } });
            if (url.pathname.endsWith("/status")) data = {
              durable_inbox_enabled: true, source_bound: state !== "empty", receipts: state === "empty" ? 0 : 1,
              by_status: state === "empty" ? {} : { failed: 1 }, backlog: state === "empty" ? 0 : 1,
              last_receipt_at: state === "empty" ? null : "2026-11-09T10:00:00", last_successful_parse_at: null,
              completeness: "not_checked", sales_live: null, legacy_receipts: "not_counted_in_this_inbox",
              why: "Receipt and parsing are separate milestones. Parsing alone does not establish complete sales coverage.",
            };
            else data = state === "empty" ? [] : [{ id: "synthetic-receipt-reference", received_at: "2026-11-09T10:00:00", status: "failed", attempts: 1, error_code: "mapping_failed", parser_version: "synthetic-v1", parsed_at: null, last_attempt_at: "2026-11-09T10:00:00", payload_sha256: "synthetic-only" }];
          } else data = { items: [], unread_count: 0 };
          return route.fulfill({ headers, json: data });
        });
        await page.goto(base + "/eleven/settings/till");
        await page.getByRole("heading", { name: "Till evidence", exact: true }).waitFor();
        if (state === "error") await page.getByRole("alert").waitFor();
        else await page.getByRole("heading", { name: "QuickSell receipt evidence" }).waitFor();
        const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        if (overflows) throw new Error(`${state} overflows at ${width}px`);
        const file = `pos-${state}-${width}.png`;
        await page.screenshot({ path: path.join(output, file), fullPage: true });
        checks.push({ state, width, horizontalOverflow: false, screenshot: file });
        await page.close();
      }
    }
    await fs.writeFile(path.join(output, "browser-results.json"), JSON.stringify({ syntheticOnly: true, checks }, null, 2) + "\n");
    console.log(`${checks.length} browser states checked; no horizontal overflow.`);
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
