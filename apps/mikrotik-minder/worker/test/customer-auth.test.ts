/**
 * SaaS Phase 1 §4 — the customer Stytch-session auth path (requireOperator).
 *
 * Generates a real RS256 keypair, serves its public key through a stubbed JWKS
 * fetch, signs session JWTs, and drives the ACTUAL worker: a valid session is
 * scoped to the org's tenant (and JIT-links a user + membership); an
 * unprovisioned org is refused; tampered / expired / wrong-key tokens are
 * rejected; and the admin-token path is untouched.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Env } from "../src/env";
import worker from "../src/index";
import { FX, migratedDb, seedTwoTenants, ShimD1 } from "./d1";

const PROJECT_ID = "project-test-abc";
const ISSUER = `stytch.com/${PROJECT_ID}`;
const JWKS_URL = `https://test.stytch.com/v1/sessions/jwks/${PROJECT_ID}`;
const KID = "jwk-test-1";
const ORG_ID = "organization-test-alpha";
const MEMBER_ID = "member-test-alpha-1";

const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
const b64urlJson = (o: unknown) => b64url(new TextEncoder().encode(JSON.stringify(o)));

// One stable keypair for the whole suite, so the worker's per-isolate JWKS cache
// (keyed by URL) stays valid across tests.
let privateKey: CryptoKey;
let jwksBody: { keys: unknown[] };

beforeAll(async () => {
  const pair = await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["sign", "verify"],
  );
  privateKey = pair.privateKey;
  const jwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
  jwksBody = { keys: [{ ...jwk, kid: KID, alg: "RS256", use: "sig" }] };
});

async function signJwt(payload: Record<string, unknown>, kid = KID): Promise<string> {
  const input = `${b64urlJson({ alg: "RS256", kid, typ: "JWT" })}.${b64urlJson(payload)}`;
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", privateKey, new TextEncoder().encode(input));
  return `${input}.${b64url(new Uint8Array(sig))}`;
}

// Mirrors the real Stytch B2B session-JWT shape: the org id lives under the
// `https://stytch.com/organization` claim (NOT a flat claim), and the email only
// inside the session's authentication factors. (A flat `organization_id` would
// pass the old extractor but never appears in a real token.)
function validPayload(
  over: { organizationId?: string; sub?: string; email?: string; iat?: number; exp?: number } = {},
): Record<string, unknown> {
  const now = Math.floor(Date.now() / 1000);
  return {
    sub: over.sub ?? MEMBER_ID,
    iss: ISSUER,
    aud: [PROJECT_ID],
    iat: over.iat ?? now,
    exp: over.exp ?? now + 3600,
    "https://stytch.com/organization": { organization_id: over.organizationId ?? ORG_ID, slug: "acme" },
    "https://stytch.com/session": {
      id: "session-test-1",
      authentication_factors: [
        { type: "magic_link", delivery_method: "email", email_factor: { email_address: over.email ?? "alpha-user@a.example" } },
      ],
    },
  };
}

function makeEnv(): { env: Env; db: ReturnType<typeof migratedDb> } {
  const db = migratedDb();
  seedTwoTenants(db);
  db.exec(`UPDATE tenants SET stytch_org_id = '${ORG_ID}' WHERE id = '${FX.tenantA}'`);
  const env: Env = {
    DB: new ShimD1(db) as unknown as Env["DB"],
    BACKUPS: { get: async () => null } as unknown as Env["BACKUPS"],
    ADMIN_TOKEN: "mtm_admin",
    MULTI_TENANT: "true",
    SUPERADMIN_EMAILS: "",
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS: "3600",
    DEFAULT_GRACE_SECONDS: "600",
    STYTCH_PROJECT_ID: PROJECT_ID,
    STYTCH_JWKS_URL: JWKS_URL,
    STYTCH_ISSUER: ISSUER,
  };
  return { env, db };
}

const get = (env: Env, path: string, token: string) =>
  worker.fetch(
    new Request(`https://minder.test${path}`, { headers: { authorization: `Bearer ${token}` } }),
    env,
    ctx,
  );

describe("customer Stytch session auth (requireOperator)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: unknown) =>
        String(url) === JWKS_URL
          ? new Response(JSON.stringify(jwksBody), { headers: { "content-type": "application/json" } })
          : new Response("not found", { status: 404 }),
      ),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("accepts a valid session and scopes to the org's tenant", async () => {
    const { env } = makeEnv();
    const res = await get(env, "/v1/admin/agents", await signJwt(validPayload()));
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).toContain(FX.nameAgentA); // the org's tenant (A)
    expect(text).not.toContain(FX.nameAgentB); // tenant B not leaked
  });

  it("JIT-links a user + tenant membership on first sight", async () => {
    const { env, db } = makeEnv();
    await get(env, "/v1/admin/agents", await signJwt(validPayload()));
    const acct = db
      .prepare("SELECT user_id FROM auth_accounts WHERE provider = 'stytch' AND provider_user_id = ?")
      .get(MEMBER_ID) as { user_id: string } | undefined;
    expect(acct).toBeTruthy();
    const mem = db
      .prepare("SELECT 1 FROM tenant_memberships WHERE tenant_id = ? AND user_id = ?")
      .get(FX.tenantA, acct!.user_id);
    expect(mem).toBeTruthy();
  });

  it("auto-provisions a fresh tenant for a new org (JIT onboarding)", async () => {
    const { env, db } = makeEnv();
    const res = await get(
      env,
      "/v1/admin/agents",
      await signJwt(validPayload({ organizationId: "organization-test-ghost", sub: "member-ghost-1" })),
    );
    expect(res.status).toBe(200);
    // A fresh tenant was created for the new org…
    const tenant = db
      .prepare("SELECT id FROM tenants WHERE stytch_org_id = ?")
      .get("organization-test-ghost") as { id: string } | undefined;
    expect(tenant).toBeTruthy();
    // …and it sees neither A's nor B's fleet (a clean, empty dashboard).
    const text = await res.text();
    expect(text).not.toContain(FX.nameAgentA);
    expect(text).not.toContain(FX.nameAgentB);
  });

  it("rejects a tampered token (401)", async () => {
    const { env } = makeEnv();
    const tok = await signJwt(validPayload());
    const tampered = tok.slice(0, -4) + (tok.slice(-4) === "AAAA" ? "BBBB" : "AAAA");
    expect((await get(env, "/v1/admin/agents", tampered)).status).toBe(401);
  });

  it("rejects an unknown signing key (401)", async () => {
    const { env } = makeEnv();
    expect((await get(env, "/v1/admin/agents", await signJwt(validPayload(), "wrong-kid"))).status).toBe(401);
  });

  it("rejects an expired session (401)", async () => {
    const { env } = makeEnv();
    const now = Math.floor(Date.now() / 1000);
    expect(
      (await get(env, "/v1/admin/agents", await signJwt(validPayload({ iat: now - 7200, exp: now - 3600 })))).status,
    ).toBe(401);
  });

  it("still accepts the admin token (legacy path preserved)", async () => {
    const { env } = makeEnv();
    const res = await worker.fetch(
      new Request("https://minder.test/v1/admin/agents", {
        headers: { authorization: "Bearer mtm_admin", "X-Auth-Email": FX.emailA },
      }),
      env,
      ctx,
    );
    expect(res.status).toBe(200);
  });
});
