import { defineConfig, devices } from "@playwright/test";

const baseURL =
  process.env.SWEEP_BASE_URL ||
  process.env.NEXT_PUBLIC_APP_URL ||
  "https://frontend-test-production-752b1b7c.up.railway.app";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /ui-broken-sweep|v11-captures/,
  timeout: 180_000,
  expect: { timeout: 25_000 },
  reporter: [["list"]],
  use: {
    baseURL,
    ...devices["Pixel 5"],
    viewport: { width: 390, height: 844 },
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
  },
});