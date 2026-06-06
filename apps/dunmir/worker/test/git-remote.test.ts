/**
 * Per-agent offsite git remote: admin set/clear/list + delivery in the agent
 * config doc (token stays a sealed blob; tenant-scoped).
 */
import { beforeEach, describe, expect, it } from "vitest";
import type { Env } from "../src/env";
import worker from "../src/index";
import { hashToken } from "../src/auth";
import { FX, migratedDb, seedTwoTenants, ShimD1 } from "./d1";

const ADMIN_TOKEN = "mtm_test_admin_token";
const AGENT_TOKEN = "mtm_agent_secret_token";
const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;

const stubBackups = { get: async () => null } as unknown as Env["BACKUPS"];

async function makeEnv(): Promise<{ env: Env; db: ReturnType<typeof migratedDb> }> {
  const db = migratedDb();
  seedTwoTenants(db);
  // Give agentA a real token hash so we can authenticate as it on /v1/ingest/*.
  db.exec(`UPDATE agents SET token_hash = '${await hashToken(AGENT_TOKEN)}' WHERE id = '${FX.agentA}'`);
  const env: Env = {
    DB: new ShimD1(db) as unknown as Env["DB"],
    BACKUPS: stubBackups,
    ADMIN_TOKEN,
    MULTI_TENANT: "true",
    SUPERADMIN_EMAILS: "root@root.example",
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS: "3600",
    DEFAULT_GRACE_SECONDS: "600",
  };
  return { env, db };
}

function admin(env: Env, path: string, opts: { method?: string; email?: string; body?: unknown } = {}) {
  const headers: Record<string, string> = { authorization: `Bearer ${ADMIN_TOKEN}` };
  if (opts.email) headers["X-Auth-Email"] = opts.email;
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  return worker.fetch(
    new Request(`https://minder.test${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    }),
    env,
    ctx,
  );
}

function agentConfig(env: Env) {
  return worker.fetch(
    new Request("https://minder.test/v1/ingest/config", {
      headers: { authorization: `Bearer ${AGENT_TOKEN}` },
    }),
    env,
    ctx,
  );
}

describe("per-agent git remote", () => {
  let env: Env;
  beforeEach(async () => {
    env = (await makeEnv()).env;
  });

  it("set → appears in the agent config doc as git.remote with the sealed token", async () => {
    const set = await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailA,
      body: {
        url: "https://github.com/platform1/dunmir-configs.git",
        branch: "prod",
        token_sealed: "SEALEDBLOB==",
      },
    });
    expect(set.status).toBe(200);

    const doc = await (await agentConfig(env)).json();
    expect(doc.git.remote.url).toBe("https://github.com/platform1/dunmir-configs.git");
    expect(doc.git.remote.branch).toBe("prod");
    expect(doc.git.remote.token_sealed).toBe("SEALEDBLOB==");
  });

  it("lists the remote (url + has-token flag) without leaking the sealed blob", async () => {
    await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailA,
      body: { url: "https://git.example/cfg.git", token_sealed: "SECRET==" },
    });
    const body = await (await admin(env, "/v1/admin/agents", { email: FX.emailA })).text();
    expect(body).toContain("https://git.example/cfg.git");
    expect(body).toContain("git_remote_has_token");
    expect(body).not.toContain("SECRET=="); // the ciphertext is never listed
  });

  it("clears the remote when url is null", async () => {
    await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailA,
      body: { url: "https://git.example/cfg.git", token_sealed: "X==" },
    });
    const cleared = await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailA,
      body: { url: null },
    });
    expect(cleared.status).toBe(200);
    const doc = await (await agentConfig(env)).json();
    expect(doc.git).toBeUndefined();
  });

  it("rejects a non-git url", async () => {
    const res = await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailA,
      body: { url: "ftp://nope" },
    });
    expect(res.status).toBe(400);
  });

  it("rejects http:// (token must not go over cleartext)", async () => {
    const res = await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailA,
      body: { url: "http://insecure.example/cfg.git" },
    });
    expect(res.status).toBe(400);
  });

  it("a body with no url is a 400, not a destructive clear", async () => {
    // First configure a remote, then send a malformed/empty body.
    await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailA,
      body: { url: "https://git.example/cfg.git", token_sealed: "BLOB==" },
    });
    const res = await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailA,
      body: {}, // url absent ⇒ must NOT clear
    });
    expect(res.status).toBe(400);
    const doc = await (await agentConfig(env)).json();
    expect(doc.git.remote.url).toBe("https://git.example/cfg.git"); // still set
  });

  it("is tenant-scoped — operator B cannot set agent A's remote", async () => {
    const res = await admin(env, `/v1/admin/agents/${FX.agentA}/git-remote`, {
      method: "POST",
      email: FX.emailB,
      body: { url: "https://evil.example/x.git" },
    });
    expect(res.status).toBe(404);
    const doc = await (await agentConfig(env)).json();
    expect(doc.git).toBeUndefined(); // unchanged
  });
});
