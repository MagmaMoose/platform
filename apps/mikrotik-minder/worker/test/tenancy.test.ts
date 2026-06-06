/**
 * Cross-tenant isolation suite — the gate before MULTI_TENANT may be enabled.
 *
 * Runs the REAL worker (its Hono app, requireAdmin, resolveTenant, and the
 * actual SQL in every handler) against an in-memory SQLite seeded with two
 * tenants. A handler that forgot its `tenant_id` filter would let one tenant's
 * resource appear in the other's response — which these assertions catch.
 */
import { beforeEach, describe, expect, it } from "vitest";
import type { Env } from "../src/env";
import worker from "../src/index";
import { FX, migratedDb, seedTwoTenants, ShimD1 } from "./d1";

const ADMIN_TOKEN = "mtm_test_admin_token";

type CallOpts = { method?: string; email?: string; body?: unknown };

// A no-op R2 bucket. The isolation tests never reach a positive R2 read (cross-
// tenant requests 404 before the storage lookup), but binding it keeps the env
// representative so a future test that does hit the download path fails cleanly
// rather than on an undefined binding.
const stubBackups = { get: async () => null } as unknown as Env["BACKUPS"];

function makeEnv(overrides: Partial<Env> = {}): { env: Env; db: ReturnType<typeof migratedDb> } {
  const db = migratedDb();
  seedTwoTenants(db);
  const env: Env = {
    // ShimD1 implements the slice of D1Database the worker uses; this is the one
    // unavoidable seam between better-sqlite3 and the Workers types.
    DB: new ShimD1(db) as unknown as Env["DB"],
    BACKUPS: stubBackups,
    ADMIN_TOKEN,
    MULTI_TENANT: "true",
    SUPERADMIN_EMAILS: "root@root.example",
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS: "3600",
    DEFAULT_GRACE_SECONDS: "600",
    ...overrides,
  };
  return { env, db };
}

const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;

function call(env: Env, path: string, opts: CallOpts = {}): Promise<Response> {
  const headers: Record<string, string> = { authorization: `Bearer ${ADMIN_TOKEN}` };
  if (opts.email) headers["X-Auth-Email"] = opts.email;
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  const req = new Request(`https://minder.test${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  return worker.fetch(req, env, ctx);
}

describe("multi-tenant admin isolation", () => {
  let env: ReturnType<typeof makeEnv>["env"];
  let db: ReturnType<typeof makeEnv>["db"];
  beforeEach(() => {
    const result = makeEnv();
    env = result.env;
    db = result.db;
  });

  it("agents list is scoped to the operator's tenant", async () => {
    const a = await (await call(env, "/v1/admin/agents", { email: FX.emailA })).text();
    expect(a).toContain(FX.nameAgentA);
    expect(a).not.toContain(FX.nameAgentB);

    const b = await (await call(env, "/v1/admin/agents", { email: FX.emailB })).text();
    expect(b).toContain(FX.nameAgentB);
    expect(b).not.toContain(FX.nameAgentA);
  });

  it("devices list is scoped to the operator's tenant", async () => {
    const a = await (await call(env, "/v1/admin/devices", { email: FX.emailA })).text();
    expect(a).toContain(FX.nameDeviceA);
    expect(a).not.toContain(FX.nameDeviceB);
  });

  it("alert routes are scoped to the operator's tenant", async () => {
    const a = await (await call(env, "/v1/admin/alert-routes", { email: FX.emailA })).text();
    expect(a).toContain(FX.nameRouteA);
    expect(a).not.toContain(FX.nameRouteB);
  });

  it("backup listing is scoped — B cannot list A's device backups", async () => {
    const own = await call(env, `/v1/admin/devices/${FX.deviceA}/backups`, { email: FX.emailA });
    expect(await own.text()).toContain(FX.fileA);

    const cross = await call(env, `/v1/admin/devices/${FX.deviceA}/backups`, { email: FX.emailB });
    expect(cross.status).toBe(200);
    expect(await cross.text()).not.toContain(FX.fileA); // empty — A's device isn't in B's tenant
  });

  it("enqueue against another tenant's device is 404 (no command created)", async () => {
    const beforeCount = (db.prepare("SELECT COUNT(*) as cnt FROM commands").get() as { cnt: number }).cnt;

    const cross = await call(env, "/v1/admin/commands", {
      method: "POST",
      email: FX.emailA,
      body: { device_id: FX.deviceB, kind: "backup" },
    });
    expect(cross.status).toBe(404);

    const afterCrossCount = (db.prepare("SELECT COUNT(*) as cnt FROM commands").get() as { cnt: number }).cnt;
    expect(afterCrossCount).toBe(beforeCount);

    const own = await call(env, "/v1/admin/commands", {
      method: "POST",
      email: FX.emailA,
      body: { device_id: FX.deviceA, kind: "backup" },
    });
    expect(own.status).toBe(201);

    const afterOwnCount = (db.prepare("SELECT COUNT(*) as cnt FROM commands").get() as { cnt: number }).cnt;
    expect(afterOwnCount).toBe(beforeCount + 1);
  });

  it("sensitive-export artifact cannot be read across tenants", async () => {
    // A tries to read B's artifact → 404, and B's secret is never returned.
    const cross = await call(env, `/v1/admin/commands/${FX.cmdB}/artifact`, { email: FX.emailA });
    expect(cross.status).toBe(404);
    expect(await cross.text()).not.toContain(FX.artifactB);

    // Verify that cross-tenant request did not purge the artifact (purge-on-read handler)
    const cmdRow = db.prepare("SELECT artifact FROM commands WHERE id = ?").get(FX.cmdB) as { artifact: string | null };
    expect(cmdRow.artifact).toBe(FX.artifactB);

    // A reads its OWN artifact: 200 + the body, delivered exactly once.
    const own = await call(env, `/v1/admin/commands/${FX.cmdA}/artifact`, { email: FX.emailA });
    expect(own.status).toBe(200);
    expect(await own.text()).toContain(FX.artifactA);
    // Purged on read — a second fetch is 410 and the DB no longer holds it.
    const again = await call(env, `/v1/admin/commands/${FX.cmdA}/artifact`, { email: FX.emailA });
    expect(again.status).toBe(410);
    const purged = db.prepare("SELECT artifact FROM commands WHERE id = ?").get(FX.cmdA) as { artifact: string | null };
    expect(purged.artifact).toBeNull();
  });

  it("backup download is refused across tenants before any storage access", async () => {
    // 404 (not 410/500): the tenant filter rejects it before the R2 lookup,
    // which is why this test needs no R2 binding.
    const cross = await call(env, `/v1/admin/backups/${FX.backupB}/download`, { email: FX.emailA });
    expect(cross.status).toBe(404);
  });

  it("an operator with no tenant membership is denied (403)", async () => {
    const res = await call(env, "/v1/admin/agents", { email: "ghost@nowhere.example" });
    expect(res.status).toBe(403);
  });
});

describe("superadmin gating", () => {
  it("tenant lifecycle requires a SUPERADMIN_EMAILS member", async () => {
    const { env } = makeEnv();
    const denied = await call(env, "/v1/superadmin/tenants", {
      method: "POST",
      email: FX.emailA, // a normal operator, not a superadmin
      body: { name: "Sneaky" },
    });
    expect(denied.status).toBe(403);

    const ok = await call(env, "/v1/superadmin/tenants", {
      method: "POST",
      email: "root@root.example",
      body: { name: "Legit" },
    });
    expect(ok.ok).toBe(true);
  });
});

describe("single-tenant inertness (MULTI_TENANT off)", () => {
  it("resolves tnt_default without any Access email and ignores other tenants", async () => {
    const { env } = makeEnv({ MULTI_TENANT: "false" });
    const res = await call(env, "/v1/admin/agents"); // no X-Auth-Email at all
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).toContain("agent-DEFAULT");
    expect(text).not.toContain(FX.nameAgentA);
    expect(text).not.toContain(FX.nameAgentB);
  });
});
