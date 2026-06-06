import { defineConfig } from "vitest/config";

// Plain Node environment: the tenancy suite runs the worker's Hono app against
// an in-memory SQLite (see test/d1.ts), so it needs no Workers/miniflare pool.
export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
  },
});
