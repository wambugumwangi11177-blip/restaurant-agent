import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_PORT || 3000);
const host = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "till-evidence-synthetic.spec.ts",
  timeout: 120_000,
  use: {
    baseURL: host,
    ...devices["Pixel 5"],
    serviceWorkers: "block",
  },
  webServer: {
    command: `npm run start -- --hostname 127.0.0.1 --port ${port}`,
    url: host,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      NEXT_PUBLIC_API_URL: host,
      NEXT_PUBLIC_SYNTHETIC_REVIEW: "1",
    },
  },
});