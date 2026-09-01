import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
    plugins: [react()],
    test: {
        environment: "jsdom",
        setupFiles: ["./vitest.setup.ts"],
        globals: true,
        // "threads" workers time out on this Windows setup ("Timeout waiting
        // for worker to respond"); forks is the reliable pool here.
        pool: "forks",
    },
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
});