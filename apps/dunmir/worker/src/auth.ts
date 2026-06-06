import type { Context, Next } from "hono";
import { type AppContext, DEFAULT_TENANT_ID } from "./env";
import { nowSeconds } from "./ids";
import { customerFromBearer } from "./stytch";

const TOKEN_PREFIX = "mtm_";

function base64url(bytes: Uint8Array): string {
  let str = "";
  for (const byte of bytes) str += String.fromCharCode(byte);
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function generateAgentToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return TOKEN_PREFIX + base64url(bytes);
}

export async function hashToken(token: string): Promise<string> {
  const data = new TextEncoder().encode(token);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return base64url(new Uint8Array(digest));
}

export function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

export function extractBearer(c: Context): string | null {
  const header = c.req.header("authorization");
  if (!header) return null;
  const match = /^Bearer\s+(.+)$/i.exec(header);
  return match ? match[1]!.trim() : null;
}

export function requireAdmin() {
  return async (c: Context<AppContext>, next: Next) => {
    const token = extractBearer(c);
    if (!token || !c.env.ADMIN_TOKEN || !constantTimeEqual(token, c.env.ADMIN_TOKEN)) {
      return c.json({ error: "unauthorized" }, 401);
    }
    c.set("isAdmin", true);
    const tenantId = await resolveTenant(c);
    if (!tenantId) {
      return c.json({ error: "no tenant for this operator" }, 403);
    }
    c.set("tenantId", tenantId);
    await next();
  };
}

/**
 * Operator auth for the customer-facing admin API: a customer **Stytch session**
 * (validated locally against the project JWKS → tenant + user) OR the shared
 * **admin token** (superadmin / internal / pre-cutover Pro, scoped via
 * X-Auth-Email). Tries the Stytch session first, so #51's validated identity
 * gates real traffic; a JWT-shaped bearer that fails to validate is rejected and
 * never falls through to the admin token. The admin-token path is retained so
 * internal flows and the not-yet-migrated Pro app keep working during the SaaS
 * migration. With STYTCH_JWKS_URL unset, this is exactly the old requireAdmin.
 */
export function requireOperator() {
  return async (c: Context<AppContext>, next: Next) => {
    const token = extractBearer(c);
    if (!token) return c.json({ error: "unauthorized" }, 401);

    // A Stytch session JWT has three dot-separated segments. When Stytch is
    // configured, a JWT-shaped bearer is treated as a customer session.
    if (c.env.STYTCH_JWKS_URL && token.split(".").length === 3) {
      const auth = await customerFromBearer(token, c.env);
      if (auth.ok) {
        c.set("tenantId", auth.tenantId);
        c.set("userId", auth.userId);
        await next();
        return;
      }
      // Valid session whose org isn't a tenant yet → 403; anything else → 401.
      return auth.reason === "no-tenant"
        ? c.json({ error: "organization is not provisioned" }, 403)
        : c.json({ error: "unauthorized" }, 401);
    }

    // Otherwise: the shared admin token (superadmin / internal / pre-cutover Pro).
    if (!c.env.ADMIN_TOKEN || !constantTimeEqual(token, c.env.ADMIN_TOKEN)) {
      return c.json({ error: "unauthorized" }, 401);
    }
    c.set("isAdmin", true);
    const tenantId = await resolveTenant(c);
    if (!tenantId) {
      return c.json({ error: "no tenant for this operator" }, 403);
    }
    c.set("tenantId", tenantId);
    await next();
  };
}

/**
 * Cross-tenant superadmin: the admin token PLUS an X-Auth-Email listed in
 * SUPERADMIN_EMAILS. Used for tenant lifecycle (create tenant, manage members),
 * which must NOT be tenant-scoped. With SUPERADMIN_EMAILS unset, nobody is a
 * superadmin (the tenant endpoints are inert) — so single-tenant deploys are
 * unaffected.
 */
export function requireSuperadmin() {
  return async (c: Context<AppContext>, next: Next) => {
    const token = extractBearer(c);
    if (!token || !c.env.ADMIN_TOKEN || !constantTimeEqual(token, c.env.ADMIN_TOKEN)) {
      return c.json({ error: "unauthorized" }, 401);
    }
    const allowed = (c.env.SUPERADMIN_EMAILS ?? "")
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter(Boolean);
    const email = (c.req.header("X-Auth-Email") ?? "").trim().toLowerCase();
    if (!email || !allowed.includes(email)) {
      return c.json({ error: "superadmin only" }, 403);
    }
    await next();
  };
}

/**
 * Resolve the tenant an admin request acts on. Single-tenant (the default) →
 * always the default tenant. Multi-tenant → the tenant the authenticated
 * operator email (X-Auth-Email, set by Cloudflare Access) is a member of;
 * an email with no membership gets no tenant (caller returns 403).
 */
export async function resolveTenant(c: Context<AppContext>): Promise<string | null> {
  if (c.env.MULTI_TENANT !== "true") {
    return DEFAULT_TENANT_ID;
  }
  const email = (c.req.header("X-Auth-Email") ?? "").trim().toLowerCase();
  if (!email) return null;
  const row = await c.env.DB.prepare("SELECT tenant_id FROM tenant_members WHERE email = ?1")
    .bind(email)
    .first<{ tenant_id: string }>();
  return row?.tenant_id ?? null;
}

export function requireAgent() {
  return async (c: Context<AppContext>, next: Next) => {
    const token = extractBearer(c);
    if (!token || !token.startsWith(TOKEN_PREFIX)) {
      return c.json({ error: "unauthorized" }, 401);
    }
    const hash = await hashToken(token);
    const row = await c.env.DB.prepare(
      "SELECT id, disabled, last_seen_at FROM agents WHERE token_hash = ?1 LIMIT 1",
    )
      .bind(hash)
      .first<{ id: string; disabled: number; last_seen_at: number | null }>();
    if (!row || row.disabled) {
      return c.json({ error: "unauthorized" }, 401);
    }
    c.set("agentId", row.id);
    // Liveness: ANY authenticated agent contact (config/commands poll, heartbeat,
    // job report) marks the agent seen — so a connected agent shows as connected
    // even before it owns a device. Throttled to ~once/min to bound D1 writes.
    const now = nowSeconds();
    if (!row.last_seen_at || now - row.last_seen_at >= 60) {
      // Also record the Cloudflare-observed egress IP here (not just on the
      // per-device heartbeat) so it's populated even when the agent owns no
      // probeable device yet — e.g. a router with no address configured.
      const ip = c.req.header("cf-connecting-ip") ?? null;
      await c.env.DB.prepare("UPDATE agents SET last_seen_at = ?1, last_ip = ?2 WHERE id = ?3")
        .bind(now, ip, row.id)
        .run();
    }
    await next();
  };
}
