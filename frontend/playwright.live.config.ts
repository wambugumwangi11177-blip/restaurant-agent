import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.LIVE_FRONTEND || "https://frontend-test-production-752b1b7c.up.railway.app",
    trace: "off",
    channel: "chrome",
  },
  projects: [{ name: "mobile", use: { ...devices["Pixel 5"], channel: "chrome", viewport: { width: 360, height: 740 } } }],
});
