import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 600_000,
  testMatch: "capture-all-states.spec.ts",
  use: {
    baseURL: "https://frontend-test-production-752b1b7c.up.railway.app",
    serviceWorkers: "block",
    ...devices["Pixel 5"],
    viewport: { width: 390, height: 844 },
  },
  projects: [{ name: "remote", testMatch: "capture-all-states.spec.ts" }],
});