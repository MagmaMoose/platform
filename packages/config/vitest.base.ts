import { defineConfig } from "vitest/config";

// Shared Vitest base — consolidates the per-worker vitest.config.ts.
export default defineConfig({
  test: {
    environment: "node",
    include: ["**/*.{test,spec}.ts"],
  },
});
