/**
 * backend/scripts/load_test.js
 * ───────────────────────────────
 * Audit remediation, Module 7 (Availability & Recovery) — "load capacity" was
 * entirely absent: no load/stress test existed anywhere in this repo. This is
 * the buildable half — write the script. Actually RUNNING it against a real
 * staging environment and interpreting results is a separate, deliberate step
 * (not something to fire at random from an agent session): it needs a
 * disposable/staging DATABASE_URL, not production, and a human watching
 * error rates and Neon connection-pool metrics live.
 *
 * What this covers, and why: the read-heavy dashboard paths (orders, menu,
 * AI analytics) an owner's screen actually hits on every page load, plus one
 * write path (order creation) since that's the one this app's own audit
 * flagged as the most likely first bottleneck at 10x traffic — see
 * ai/spend_cap.py and rate_limit.py's docstring on the single-gunicorn-worker
 * constraint. This script is what would prove or disprove that finding with
 * real numbers instead of code-reading inference.
 *
 * Requires k6 (https://k6.io) — not installed in this environment, not a
 * pip/npm package. Install separately, then:
 *
 *   BASE_URL=https://staging.example.com \
 *   LOGIN_EMAIL=owner@example.com \
 *   LOGIN_PASSWORD=... \
 *   k6 run backend/scripts/load_test.js
 *
 * Defaults to http://localhost:8000 with the local dev seed credentials from
 * execution/seed_local_dev_db.py if the env vars above aren't set — safe for
 * a quick local smoke run, never point this at production.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const LOGIN_EMAIL = __ENV.LOGIN_EMAIL || "owner@dev.local";
const LOGIN_PASSWORD = __ENV.LOGIN_PASSWORD || "DevTest2026!";

// Custom metrics so a run's summary answers "did anything actually break"
// and "how slow did it get", not just k6's generic aggregate.
const errorRate = new Rate("app_errors");
const orderCreateDuration = new Trend("order_create_duration");

export const options = {
  // Staged ramp, not a flat spike — mirrors a real service opening (covers
  // arriving over ~10 minutes), not a synthetic instant-10x step that no
  // real traffic pattern looks like. Tune target for what "10x" means for
  // your actual baseline.
  stages: [
    { duration: "1m", target: 10 },   // warm up
    { duration: "3m", target: 50 },   // baseline-ish
    { duration: "3m", target: 200 },  // the "10x" case this audit flagged
    { duration: "2m", target: 200 },  // hold, see if it degrades over time
    { duration: "1m", target: 0 },    // ramp down
  ],
  thresholds: {
    // Fails the run (non-zero exit) if either trips — the numbers that
    // matter more than the raw p95, since a slow-but-working app and a
    // fast-but-erroring app look identical on latency alone.
    http_req_failed: ["rate<0.01"],       // <1% hard failures
    app_errors: ["rate<0.05"],             // <5% non-2xx on endpoints we expect 2xx from
    http_req_duration: ["p(95)<2000"],     // 2s p95 — adjust to your own SLO
  },
};

function login() {
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: LOGIN_EMAIL, password: LOGIN_PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );
  const ok = check(res, { "login succeeded": (r) => r.status === 200 });
  errorRate.add(!ok);
  if (!ok) return null;
  return res.json("access_token");
}

export default function () {
  const token = login();
  if (!token) {
    sleep(1);
    return;
  }
  const authHeaders = { headers: { Authorization: `Bearer ${token}` } };

  // Read-heavy paths — what an owner's dashboard actually fires on load.
  const menu = http.get(`${BASE_URL}/api/v1/menu/`, authHeaders);
  errorRate.add(!check(menu, { "menu 200": (r) => r.status === 200 }));

  const activeOrders = http.get(`${BASE_URL}/api/v1/orders/active`, authHeaders);
  errorRate.add(!check(activeOrders, { "active orders 200": (r) => r.status === 200 }));

  const pricing = http.get(`${BASE_URL}/api/v1/ai/pricing?narrate=false`, authHeaders);
  errorRate.add(!check(pricing, { "ai pricing 200 or 429": (r) => r.status === 200 || r.status === 429 }));
  // 429 is an ACCEPTABLE outcome here, not a failure — rate_limit.py and
  // ai/spend_cap.py are supposed to reject some fraction of this traffic
  // under real load. A 5xx would not be acceptable; a 429 is the system
  // working as designed.

  sleep(1);

  // One write path per iteration — order creation, the checkout flow this
  // whole app exists for. menu.json()[0] assumes the seed data has at least
  // one item; a real staging run should seed accordingly first.
  const items = menu.json();
  if (Array.isArray(items) && items.length > 0) {
    const start = Date.now();
    const orderRes = http.post(
      `${BASE_URL}/api/v1/orders/`,
      JSON.stringify({
        items: [{ menu_item_id: items[0].id, quantity: 1 }],
        order_type: "dine_in",
        delivery_channel: "walk_in",
        payment_method: "pending",
        customer_name: "",
        customer_phone: "",
        table_number: null,
        notes: "",
      }),
      { headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` } }
    );
    orderCreateDuration.add(Date.now() - start);
    errorRate.add(!check(orderRes, { "order create 201": (r) => r.status === 201 }));
  }

  sleep(1);
}
