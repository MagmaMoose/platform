import { Hono } from "hono";
import { requireSuperadmin } from "../auth";
import type { AppContext } from "../env";
import { newId, nowSeconds } from "../ids";
import { asString } from "../schema";

// Tenant lifecycle (superadmin only). Mounted at /v1/superadmin/tenants so it
// bypasses the tenant-scoping requireAdmin middleware — these ops are cross-tenant.
const tenants = new Hono<AppContext>();
tenants.use("*", requireSuperadmin());

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

tenants.post("/", async (c) => {
  const body = await c.req.json().catch(() => null);
  const name = asString(body?.name, "name", { max: 100 });
  if (!name.ok) return c.json({ error: name.error }, 400);
  const id = newId("tnt");
  const now = nowSeconds();
  await c.env.DB.prepare("INSERT INTO tenants (id, name, created_at) VALUES (?1, ?2, ?3)")
    .bind(id, name.value, now)
    .run();
  return c.json({ id, name: name.value, created_at: now }, 201);
});

tenants.get("/", async (c) => {
  const { results } = await c.env.DB.prepare(
    "SELECT id, name, created_at FROM tenants ORDER BY created_at DESC",
  ).all();
  return c.json({ tenants: results });
});

// Map an operator email to a tenant. An email belongs to exactly one tenant, so
// re-adding it moves it (upsert on the email primary key).
tenants.post("/:id/members", async (c) => {
  const tenantId = c.req.param("id");
  const body = await c.req.json().catch(() => null);
  const email = asString(body?.email, "email", { max: 254, pattern: EMAIL_RE });
  if (!email.ok) return c.json({ error: email.error }, 400);
  const tenant = await c.env.DB.prepare("SELECT id FROM tenants WHERE id = ?1")
    .bind(tenantId)
    .first();
  if (!tenant) return c.json({ error: "tenant not found" }, 404);
  await c.env.DB.prepare(
    `INSERT INTO tenant_members (email, tenant_id, created_at) VALUES (?1, ?2, ?3)
     ON CONFLICT(email) DO UPDATE SET tenant_id = excluded.tenant_id`,
  )
    .bind(email.value.toLowerCase(), tenantId, nowSeconds())
    .run();
  return c.json({ email: email.value.toLowerCase(), tenant_id: tenantId }, 201);
});

tenants.get("/:id/members", async (c) => {
  const { results } = await c.env.DB.prepare(
    "SELECT email, created_at FROM tenant_members WHERE tenant_id = ?1 ORDER BY email",
  )
    .bind(c.req.param("id"))
    .all();
  return c.json({ members: results });
});

tenants.delete("/:id/members/:email", async (c) => {
  const res = await c.env.DB.prepare(
    "DELETE FROM tenant_members WHERE tenant_id = ?1 AND email = ?2",
  )
    .bind(c.req.param("id"), decodeURIComponent(c.req.param("email")).toLowerCase())
    .run();
  if ((res.meta.changes ?? 0) === 0) return c.json({ error: "not found" }, 404);
  return c.json({ ok: true });
});

export default tenants;
