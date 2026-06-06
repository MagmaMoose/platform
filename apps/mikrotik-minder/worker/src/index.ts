import { Hono } from "hono";
import type { AppContext, Env } from "./env";
import admin from "./routes/admin";
import ingest from "./routes/ingest";
import tenants from "./routes/tenants";
import { runScheduledSweep } from "./scheduled";

const app = new Hono<AppContext>();

app.onError((err, c) => {
  console.error("unhandled", err);
  return c.json({ error: "internal_error" }, 500);
});

app.notFound((c) => c.json({ error: "not_found" }, 404));

// Public liveness probe + a "what is this" landing JSON so people who hit the
// bare hostname know what they've found. No state, no auth.
app.get("/", (c) =>
  c.json({
    service: "mikrotik-minder",
    docs: "https://github.com/magmamoose/mikrotik-minder",
    endpoints: {
      ingest: "/v1/ingest/*",
      admin: "/v1/admin/*",
      health: "/v1/health",
    },
  }),
);

app.get("/v1/health", (c) => c.json({ ok: true, service: "mikrotik-minder" }));

app.route("/v1/ingest", ingest);
app.route("/v1/admin", admin);
// Cross-tenant superadmin (tenant lifecycle); gated by SUPERADMIN_EMAILS.
app.route("/v1/superadmin/tenants", tenants);

export default {
  fetch: app.fetch,
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(runScheduledSweep(env, ctx));
  },
} satisfies ExportedHandler<Env>;
