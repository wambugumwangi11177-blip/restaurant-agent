import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_PORT || 3456);
const host = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: {
    baseURL: host,
    trace: "off",
  },
  webServer: {
    command: `npx next start -p ${port}`,
    url: host,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      NEXT_PUBLIC_API_URL: host,
    },
  },
  projects: [{ name: "mobile", use: { ...devices["Pixel 5"], viewport: { width: 360, height: 740 } } }],
});