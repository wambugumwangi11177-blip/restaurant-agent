import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

/**
 * E6 — owner tasks (docs/v2/SPEC.md §5): the owner finds the answer, at a phone's width and a desk's, with no console error.
 * The stack is started here: the real backend on a throwaway SQLite demo (execution/e6_backend.py) and the production build of the
 * frontend. The browser is the one already installed in this environment (PLAYWRIGHT_BROWSERS_PATH); nothing is downloaded.
 */
const CHROMIUM = process.env.E6_CHROMIUM ?? ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome-linux/chrome"].find(existsSync);
const PYTHON = process.env.PY ?? "python3";
const reuse = Boolean(process.env.E6_REUSE);      // while developing: use servers that are already running
// A browser in a sandbox with a proxy only: do not let it wait on update, sync or safe-browsing services it cannot reach.
const QUIET = ["--no-sandbox", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-default-apps", "--no-first-run", "--disable-client-side-phishing-detection", "--metrics-recording-only"];

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3000", launchOptions: { executablePath: CHROMIUM, args: QUIET } },
  projects: [
    { name: "phone-390", use: { ...devices["Pixel 5"], viewport: { width: 390, height: 844 }, launchOptions: { executablePath: CHROMIUM, args: QUIET } } },
    { name: "desk-1440", use: { viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    { command: `${PYTHON} ../execution/e6_backend.py`, url: "http://127.0.0.1:8000/health", timeout: 180_000, reuseExistingServer: reuse },
    { command: "npx next start -p 3000", url: "http://localhost:3000/login", timeout: 60_000, reuseExistingServer: reuse },
  ],
});
