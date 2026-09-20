import { defineConfig } from "vitest/config";
import path from "node:path";

// Unit tests for pure logic only — routing decisions, the permission matrix,
// formatters. No jsdom and no component rendering: those need a browser
// environment and a much bigger dependency surface, and the bugs that actually
// reached production here were in pure functions. A waiter was dropped on a
// dead page because homeFor() looked at the tenant and not the role; that is a
// three-line function and a test that would have caught it costs nothing.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    reporters: ["default"],
  },
  resolve: {
    // Mirrors the `@/*` path in tsconfig.json. Set by hand rather than pulling
    // in vite-tsconfig-paths for one alias.
    alias: { "@": path.resolve(__dirname, "src") },
  },
});
