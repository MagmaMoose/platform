import { Hono } from "hono";
import type { AppContext } from "../env";
import { generateAgentToken, hashToken, requireOperator } from "../auth";
import { newId, nowSeconds } from "../ids";
import {
  ALERT_KINDS,
  asEnum,
  asInt,
  asOptionalBool,
  asOptionalEnum,
  asOptionalInt,
  asOptionalString,
  asString,
  asStringArray,
  COMMAND_KINDS,
  ROUTE_KINDS,
  SEVERITIES,
  TRANSPORTS,
  type AlertKind,
  type Severity,
} from "../schema";
import { fireAlert } from "../notify";

const admin = new Hono<AppContext>();
admin.use("*", requireOperator());

// --- Agents ---------------------------------------------------------------

admin.post("/agents", async (c) => {
  const body = await c.req.json().catch(() => null);
  const name = asString(body?.name, "name", { max: 100 });
  if (!name.ok) return c.json({ error: name.error }, 400);

  const token = generateAgentToken();
  const tokenHash = await hashToken(token);
  const id = newId("agent");
  const now = nowSeconds();
  try {
    await c.env.DB.prepare(
      "INSERT INTO agents (id, name, token_hash, created_at, tenant_id) VALUES (?1, ?2, ?3, ?4, ?5)",
    )
      .bind(id, name.value, tokenHash, now, c.get("tenantId")!)
      .run();
  } catch (err) {
    if (String(err).includes("UNIQUE")) return c.json({ error: "agent name already exists" }, 409);
    throw err;
  }
  return c.json({ id, name: name.value, token, created_at: now }, 201);
});

admin.get("/agents", async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT id, name, created_at, last_seen_at, disabled, public_key,
            git_remote_url, git_remote_branch,
            CASE WHEN git_remote_token_sealed IS NOT NULL THEN 1 ELSE 0 END AS git_remote_has_token
       FROM agents WHERE tenant_id = ?1 ORDER BY created_at DESC`,
  )
    .bind(c.get("tenantId")!)
    .all();
  return c.json({ agents: results });
});

admin.post("/agents/:id/disable", async (c) => {
  const id = c.req.param("id");
  const res = await c.env.DB.prepare(
    "UPDATE agents SET disabled = 1 WHERE id = ?1 AND tenant_id = ?2",
  )
    .bind(id, c.get("tenantId")!)
    .run();
  if ((res.meta.changes ?? 0) === 0) return c.json({ error: "not found" }, 404);
  return c.json({ ok: true });
});

admin.post("/agents/:id/rotate-token", async (c) => {
  const id = c.req.param("id");
  const token = generateAgentToken();
  const tokenHash = await hashToken(token);
  const res = await c.env.DB.prepare(
    "UPDATE agents SET token_hash = ?1, disabled = 0 WHERE id = ?2 AND tenant_id = ?3",
  )
    .bind(tokenHash, id, c.get("tenantId")!)
    .run();
  if ((res.meta.changes ?? 0) === 0) return c.json({ error: "not found" }, 404);
  return c.json({ id, token });
});

// Set (or clear) the agent's offsite git remote for config-export history.
// The token arrives SEALED (sealed-box to the agent's public key) from the
// browser — the worker stores ciphertext only, never the plaintext token.
// Body: { url, branch?, token_sealed? }. url=null/"" clears the whole remote.
// token_sealed omitted ⇒ keep existing; null/"" ⇒ clear token; string ⇒ set.
admin.post("/agents/:id/git-remote", async (c) => {
  const id = c.req.param("id");
  const tenantId = c.get("tenantId")!;
  const body = await c.req.json().catch(() => null);
  if (body === null || typeof body !== "object") {
    return c.json({ error: "invalid JSON body" }, 400);
  }
  const fields = body as Record<string, unknown>;

  // Clearing the remote must be EXPLICIT: `url` present and null/"". A missing or
  // malformed body is a 400 — never a destructive clear of an absent field.
  if ("url" in fields && (fields.url === null || fields.url === "")) {
    const res = await c.env.DB.prepare(
      `UPDATE agents SET git_remote_url = NULL, git_remote_branch = NULL,
         git_remote_token_sealed = NULL WHERE id = ?1 AND tenant_id = ?2`,
    )
      .bind(id, tenantId)
      .run();
    if ((res.meta.changes ?? 0) === 0) return c.json({ error: "agent not found" }, 404);
    return c.json({ ok: true, cleared: true });
  }

  const url = asString(fields.url, "url", { max: 500 });
  if (!url.ok) return c.json({ error: url.error }, 400);
  // https only (not http): a token must never be pushed over cleartext.
  if (!/^(https:\/\/|ssh:\/\/|git@)/.test(url.value)) {
    return c.json({ error: "url must be an https://, ssh://, or git@ remote" }, 400);
  }
  const branch = asOptionalString(fields.branch, "branch", { max: 100 });
  if (!branch.ok) return c.json({ error: branch.error }, 400);

  const sealed = fields.token_sealed;
  if (sealed !== null && sealed !== undefined && typeof sealed !== "string") {
    return c.json({ error: "token_sealed must be a string or null" }, 400);
  }
  if (typeof sealed === "string" && sealed.length > 10000) {
    return c.json({ error: "token_sealed exceeds 10000 chars" }, 400);
  }

  // token_sealed omitted ⇒ leave the existing token untouched (lets an operator
  // change the branch without re-pasting the token).
  const stmt =
    sealed === undefined
      ? c.env.DB.prepare(
          `UPDATE agents SET git_remote_url = ?1, git_remote_branch = ?2
             WHERE id = ?3 AND tenant_id = ?4`,
        ).bind(url.value, branch.value ?? "main", id, tenantId)
      : c.env.DB.prepare(
          `UPDATE agents SET git_remote_url = ?1, git_remote_branch = ?2,
             git_remote_token_sealed = ?3 WHERE id = ?4 AND tenant_id = ?5`,
        ).bind(url.value, branch.value ?? "main", sealed || null, id, tenantId);
  const res = await stmt.run();
  if ((res.meta.changes ?? 0) === 0) return c.json({ error: "agent not found" }, 404);
  return c.json({ ok: true });
});

// Delete an agent and ALL its devices (danger zone). Devices are removed first
// so none dangle if FK enforcement is off; both statements are tenant-scoped.
admin.delete("/agents/:id", async (c) => {
  const id = c.req.param("id");
  const tenantId = c.get("tenantId")!;
  const results = await c.env.DB.batch([
    c.env.DB.prepare(
      "DELETE FROM devices WHERE agent_id = ?1 AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?2)",
    ).bind(id, tenantId),
    c.env.DB.prepare("DELETE FROM agents WHERE id = ?1 AND tenant_id = ?2").bind(id, tenantId),
  ]);
  if ((results[1]?.meta.changes ?? 0) === 0) return c.json({ error: "not found" }, 404);
  return c.json({ ok: true });
});

// --- Devices --------------------------------------------------------------

admin.post("/devices", async (c) => {
  const body = await c.req.json().catch(() => null);
  const agentId = asString(body?.agent_id, "agent_id");
  if (!agentId.ok) return c.json({ error: agentId.error }, 400);
  const name = asString(body?.name, "name", { max: 100 });
  if (!name.ok) return c.json({ error: name.error }, 400);
  const site = asOptionalString(body?.site, "site", { max: 100 });
  if (!site.ok) return c.json({ error: site.error }, 400);
  const role = asOptionalString(body?.role, "role", { max: 100 });
  if (!role.ok) return c.json({ error: role.error }, 400);
  const tags = asStringArray(body?.tags, "tags");
  if (!tags.ok) return c.json({ error: tags.error }, 400);
  const interval = asOptionalInt(body?.heartbeat_interval_seconds, "heartbeat_interval_seconds", {
    min: 30,
    max: 86400,
  });
  if (!interval.ok) return c.json({ error: interval.error }, 400);
  const grace = asOptionalInt(body?.grace_seconds, "grace_seconds", { min: 0, max: 86400 });
  if (!grace.ok) return c.json({ error: grace.error }, 400);
  // Display label — what the UI shows. `name` stays the immutable agent match-key.
  const label = asOptionalString(body?.label, "label", { max: 100 });
  if (!label.ok) return c.json({ error: label.error }, 400);

  // Connection details (control-plane-managed config). All optional; credentials
  // are stored only as references (env-var name / key path), never as secrets.
  const address = asOptionalString(body?.address, "address", { max: 255 });
  if (!address.ok) return c.json({ error: address.error }, 400);
  const username = asOptionalString(body?.username, "username", { max: 100 });
  if (!username.ok) return c.json({ error: username.error }, 400);
  const passwordEnv = asOptionalString(body?.password_env, "password_env", { max: 100 });
  if (!passwordEnv.ok) return c.json({ error: passwordEnv.error }, 400);
  const sshKeyPath = asOptionalString(body?.ssh_key_path, "ssh_key_path", { max: 255 });
  if (!sshKeyPath.ok) return c.json({ error: sshKeyPath.error }, 400);
  const tPrimary = asOptionalEnum(body?.transport_primary, "transport_primary", TRANSPORTS);
  if (!tPrimary.ok) return c.json({ error: tPrimary.error }, 400);
  const tFallback = asOptionalEnum(body?.transport_fallback, "transport_fallback", TRANSPORTS);
  if (!tFallback.ok) return c.json({ error: tFallback.error }, 400);
  const apiPort = asOptionalInt(body?.api_port, "api_port", { min: 1, max: 65535 });
  if (!apiPort.ok) return c.json({ error: apiPort.error }, 400);
  const sshPort = asOptionalInt(body?.ssh_port, "ssh_port", { min: 1, max: 65535 });
  if (!sshPort.ok) return c.json({ error: sshPort.error }, 400);
  const useTls = asOptionalBool(body?.use_tls, "use_tls");
  if (!useTls.ok) return c.json({ error: useTls.error }, 400);
  const useTlsInt = useTls.value === undefined ? null : useTls.value ? 1 : 0;

  const agent = await c.env.DB.prepare(
    "SELECT id FROM agents WHERE id = ?1 AND disabled = 0 AND tenant_id = ?2",
  )
    .bind(agentId.value, c.get("tenantId")!)
    .first();
  if (!agent) return c.json({ error: "agent not found" }, 404);

  const existing = await c.env.DB.prepare(
    "SELECT id FROM devices WHERE agent_id = ?1 AND name = ?2",
  )
    .bind(agentId.value, name.value)
    .first<{ id: string }>();

  const id = existing?.id ?? newId("dev");
  const now = nowSeconds();
  const tagsJson = tags.value ? JSON.stringify(tags.value) : null;

  if (existing) {
    // COALESCE(?, col): a field the caller OMITS (e.g. an empty input from a
    // stale edit form) keeps its current value instead of being nulled. So
    // editing one field can never silently wipe another. (To intentionally clear
    // a field, that needs an explicit path — none of the UI forms clear these.)
    await c.env.DB.prepare(
      `UPDATE devices SET
         site = COALESCE(?1, site), role = COALESCE(?2, role), tags = COALESCE(?3, tags),
         heartbeat_interval_seconds = COALESCE(?4, heartbeat_interval_seconds),
         grace_seconds = COALESCE(?5, grace_seconds),
         address = COALESCE(?6, address), username = COALESCE(?7, username),
         password_env = COALESCE(?8, password_env), ssh_key_path = COALESCE(?9, ssh_key_path),
         transport_primary = COALESCE(?10, transport_primary),
         transport_fallback = COALESCE(?11, transport_fallback),
         api_port = COALESCE(?12, api_port), use_tls = COALESCE(?13, use_tls),
         ssh_port = COALESCE(?14, ssh_port), label = COALESCE(?15, label)
       WHERE id = ?16`,
    )
      .bind(
        site.value ?? null,
        role.value ?? null,
        tagsJson,
        interval.value ?? null,
        grace.value ?? null,
        address.value ?? null,
        username.value ?? null,
        passwordEnv.value ?? null,
        sshKeyPath.value ?? null,
        tPrimary.value ?? null,
        tFallback.value ?? null,
        apiPort.value ?? null,
        useTlsInt,
        sshPort.value ?? null,
        label.value ?? null,
        id,
      )
      .run();
  } else {
    await c.env.DB.prepare(
      `INSERT INTO devices
       (id, agent_id, name, site, role, tags, heartbeat_interval_seconds, grace_seconds,
        address, username, password_env, ssh_key_path, transport_primary, transport_fallback,
        api_port, use_tls, ssh_port, label, last_status, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, 'unknown', ?19)`,
    )
      .bind(
        id,
        agentId.value,
        name.value,
        site.value ?? null,
        role.value ?? null,
        tagsJson,
        interval.value ?? null,
        grace.value ?? null,
        address.value ?? null,
        username.value ?? null,
        passwordEnv.value ?? null,
        sshKeyPath.value ?? null,
        tPrimary.value ?? null,
        tFallback.value ?? null,
        apiPort.value ?? null,
        useTlsInt,
        sshPort.value ?? null,
        label.value ?? null,
        now,
      )
      .run();
  }
  return c.json({ id, upserted: !existing });
});

admin.get("/devices", async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT id, agent_id, name, site, role, tags, heartbeat_interval_seconds, grace_seconds,
            last_seen_at, last_status, last_status_changed_at, created_at
     FROM devices WHERE agent_id IN (SELECT id FROM agents WHERE tenant_id = ?1) ORDER BY name`,
  )
    .bind(c.get("tenantId")!)
    .all();
  return c.json({ devices: results });
});

admin.delete("/devices/:id", async (c) => {
  const res = await c.env.DB.prepare(
    "DELETE FROM devices WHERE id = ?1 AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?2)",
  )
    .bind(c.req.param("id"), c.get("tenantId")!)
    .run();
  if ((res.meta.changes ?? 0) === 0) return c.json({ error: "not found" }, 404);
  return c.json({ ok: true });
});

// Move a device to a different agent in the same tenant. The device keeps its id
// (and history); only its owning agent changes.
admin.post("/devices/:id/reassign", async (c) => {
  const id = c.req.param("id");
  const body = await c.req.json().catch(() => null);
  const agentId = asString(body?.agent_id, "agent_id");
  if (!agentId.ok) return c.json({ error: agentId.error }, 400);
  const tenantId = c.get("tenantId")!;
  const agent = await c.env.DB.prepare(
    "SELECT id FROM agents WHERE id = ?1 AND tenant_id = ?2 AND disabled = 0",
  )
    .bind(agentId.value, tenantId)
    .first();
  if (!agent) return c.json({ error: "agent not found" }, 404);
  try {
    const res = await c.env.DB.prepare(
      "UPDATE devices SET agent_id = ?1 WHERE id = ?2 AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?3)",
    )
      .bind(agentId.value, id, tenantId)
      .run();
    if ((res.meta.changes ?? 0) === 0) return c.json({ error: "device not found" }, 404);
  } catch (err) {
    if (String(err).includes("UNIQUE")) {
      return c.json({ error: "that agent already has a device with this name" }, 409);
    }
    throw err;
  }
  return c.json({ ok: true });
});

// Set (or clear, with null) a device's sealed credential — a libsodium sealed-box
// ciphertext the licensed UI produces by encrypting to the agent's public key.
// The worker stores it opaquely; GET /v1/ingest/config then serves it as
// credential.kind = "sealed". The plane never sees the plaintext or a key.
admin.post("/devices/:id/sealed-credential", async (c) => {
  const body = await c.req.json().catch(() => null);
  const sealed = body?.sealed;
  if (sealed !== null && sealed !== undefined && typeof sealed !== "string") {
    return c.json({ error: "sealed must be a string (to set) or null (to clear)" }, 400);
  }
  if (typeof sealed === "string" && sealed.length > 10000) {
    return c.json({ error: "sealed blob exceeds 10000 chars" }, 400);
  }
  const res = await c.env.DB.prepare(
    `UPDATE devices SET credential_sealed = ?1
       WHERE id = ?2 AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?3)`,
  )
    .bind(sealed ?? null, c.req.param("id"), c.get("tenantId")!)
    .run();
  if ((res.meta.changes ?? 0) === 0) return c.json({ error: "not found" }, 404);
  return c.json({ ok: true });
});

// --- Alert routes ---------------------------------------------------------

admin.post("/alert-routes", async (c) => {
  const body = await c.req.json().catch(() => null);
  const name = asString(body?.name, "name", { max: 100 });
  if (!name.ok) return c.json({ error: name.error }, 400);
  const kind = asEnum(body?.kind, "kind", ROUTE_KINDS);
  if (!kind.ok) return c.json({ error: kind.error }, 400);
  const url = asString(body?.url, "url", { max: 1000, pattern: /^https?:\/\// });
  if (!url.ok) return c.json({ error: url.error }, 400);
  const events = asStringArray(body?.events, "events");
  if (!events.ok) return c.json({ error: events.error }, 400);
  if (events.value) {
    for (const ev of events.value) {
      if (!ALERT_KINDS.includes(ev as AlertKind)) {
        return c.json({ error: `unknown event '${ev}'` }, 400);
      }
    }
  }
  const minSeverity: Severity = body?.min_severity ?? "warning";
  if (!SEVERITIES.includes(minSeverity)) return c.json({ error: "invalid min_severity" }, 400);

  const id = newId("route");
  try {
    await c.env.DB.prepare(
      `INSERT INTO alert_routes (id, name, kind, url, events, min_severity, enabled, created_at, tenant_id)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1, ?7, ?8)`,
    )
      .bind(
        id,
        name.value,
        kind.value,
        url.value,
        events.value ? JSON.stringify(events.value) : null,
        minSeverity,
        nowSeconds(),
        c.get("tenantId")!,
      )
      .run();
  } catch (err) {
    if (String(err).includes("UNIQUE")) return c.json({ error: "route name already exists" }, 409);
    throw err;
  }
  return c.json({ id, name: name.value }, 201);
});

admin.get("/alert-routes", async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT id, name, kind, url, events, min_severity, enabled, created_at
       FROM alert_routes WHERE tenant_id = ?1 ORDER BY name`,
  )
    .bind(c.get("tenantId")!)
    .all();
  return c.json({ routes: results });
});

admin.delete("/alert-routes/:id", async (c) => {
  const res = await c.env.DB.prepare(
    "DELETE FROM alert_routes WHERE id = ?1 AND tenant_id = ?2",
  )
    .bind(c.req.param("id"), c.get("tenantId")!)
    .run();
  if ((res.meta.changes ?? 0) === 0) return c.json({ error: "not found" }, 404);
  return c.json({ ok: true });
});

// --- Test alert -----------------------------------------------------------

admin.post("/alerts/test", async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const message = typeof body?.message === "string" ? body.message : "Test alert from Mikrotik Minder";
  // Pass executionCtx so the outbound webhook fan-out runs via waitUntil()
  // and the API can respond immediately after persisting the alert row.
  // Otherwise a slow Slack/Discord sink would block this endpoint.
  const alertId = await fireAlert(
    c.env,
    {
      severity: "info",
      kind: "manual",
      title: message,
      payload: { source: "admin", note: "manual test" },
      tenant_id: c.get("tenantId")!,
    },
    c.executionCtx,
  );
  return c.json({ ok: true, alert_id: alertId });
});

// --- Commands -------------------------------------------------------------
// The Pro UI enqueues operator-triggered actions here; the agent claims them
// via GET /v1/ingest/commands and reports back via POST .../result.

admin.post("/commands", async (c) => {
  const body = await c.req.json().catch(() => null);
  const deviceId = asString(body?.device_id, "device_id", { max: 100 });
  if (!deviceId.ok) return c.json({ error: deviceId.error }, 400);
  const kind = asEnum(body?.kind, "kind", COMMAND_KINDS);
  if (!kind.ok) return c.json({ error: kind.error }, 400);
  const scheduledFor = asOptionalInt(body?.scheduled_for, "scheduled_for", { min: 0 });
  if (!scheduledFor.ok) return c.json({ error: scheduledFor.error }, 400);
  // Derive requested_by from the X-Auth-Email header (set by Cloudflare Access)
  const rawEmail = c.req.header("X-Auth-Email") ?? "";
  const trimmed = rawEmail.trim();
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const requestedBy = trimmed.length > 0 && trimmed.length <= 254 && emailRegex.test(trimmed) ? trimmed : "unknown";
  const params = body?.params;
  if (
    params !== undefined &&
    (typeof params !== "object" || params === null || Array.isArray(params))
  ) {
    return c.json({ error: "params must be an object" }, 400);
  }

  const dev = await c.env.DB.prepare(
    `SELECT id, agent_id FROM devices
       WHERE id = ?1 AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?2)`,
  )
    .bind(deviceId.value, c.get("tenantId")!)
    .first<{ id: string; agent_id: string }>();
  if (!dev) return c.json({ error: "device not found" }, 404);

  const id = newId("cmd");
  await c.env.DB.prepare(
    `INSERT INTO commands
       (id, device_id, agent_id, kind, params, status, scheduled_for, requested_by, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, 'pending', ?6, ?7, ?8)`,
  )
    .bind(
      id,
      dev.id,
      dev.agent_id,
      kind.value,
      params !== undefined ? JSON.stringify(params) : null,
      scheduledFor.value ?? null,
      requestedBy,
      nowSeconds(),
    )
    .run();
  return c.json({ id, status: "pending" }, 201);
});

// One-shot download of a sensitive-export artifact. Purged on read — the
// secret-bearing /export body is delivered exactly once and never re-served.
admin.get("/commands/:id/artifact", async (c) => {
  const id = c.req.param("id");
  const tenantId = c.get("tenantId")!;
  // Read the (tenant-scoped) artifact, THEN null it — two statements rather than
  // a single UPDATE…RETURNING. A self-referencing CTE (`RETURNING (SELECT … FROM
  // old)`) re-evaluates `old` AFTER the row is nulled on modern SQLite, so it
  // returns NULL and the body is lost (MATERIALIZED doesn't help). The purge is
  // still guarded by `artifact IS NOT NULL` so a re-read can't re-serve it.
  const row = await c.env.DB.prepare(
    `SELECT artifact FROM commands
       WHERE id = ?1 AND artifact IS NOT NULL
         AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?2)`,
  )
    .bind(id, tenantId)
    .first<{ artifact: string | null }>();
  if (!row || row.artifact === null) {
    // Either the row doesn't exist (for this tenant), or artifact was already
    // NULL (already downloaded).
    const cmd = await c.env.DB.prepare(
      "SELECT id, status FROM commands WHERE id = ?1 AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?2)",
    )
      .bind(id, tenantId)
      .first<{ id: string; status: string }>();
    if (!cmd) return c.json({ error: "not found" }, 404);
    if (cmd.status === "pending" || cmd.status === "claimed") {
      return c.json({ error: "command not yet ready" }, 202);
    }
    return c.json({ error: "no artifact — already downloaded, or none produced" }, 410);
  }
  // Purge on read — scoped + guarded so it only ever clears this tenant's row.
  await c.env.DB.prepare(
    `UPDATE commands SET artifact = NULL
       WHERE id = ?1 AND artifact IS NOT NULL
         AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?2)`,
  )
    .bind(id, tenantId)
    .run();
  return c.text(row.artifact, 200, {
    "content-type": "text/plain; charset=utf-8",
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
  });
});

// --- Backups --------------------------------------------------------------
// The agent uploads encrypted backups via PUT /v1/ingest/backups/...; these
// admin endpoints let the Pro UI list and download them. The body in R2 is
// already AES-encrypted by RouterOS, so the worker never holds plaintext.

admin.get("/devices/:id/backups", async (c) => {
  const id = c.req.param("id");
  const { results } = await c.env.DB.prepare(
    `SELECT id, file_name, size_bytes, sha256, created_at
       FROM backup_files
      WHERE device_id = ?1
        AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?2)
   ORDER BY created_at DESC
      LIMIT 200`,
  )
    .bind(id, c.get("tenantId")!)
    .all();
  return c.json({ backups: results });
});

// Stream the encrypted backup body from R2. The Pro UI proxies this so the
// browser never talks to R2 directly. No caching headers — the body is a
// sensitive ciphertext blob, and we don't want intermediates retaining it.
admin.get("/backups/:id/download", async (c) => {
  const id = c.req.param("id");
  const row = await c.env.DB.prepare(
    `SELECT file_name, r2_key, sha256 FROM backup_files
       WHERE id = ?1 AND agent_id IN (SELECT id FROM agents WHERE tenant_id = ?2)`,
  )
    .bind(id, c.get("tenantId")!)
    .first<{ file_name: string; r2_key: string; sha256: string }>();
  if (!row) return c.json({ error: "not found" }, 404);

  const obj = await c.env.BACKUPS.get(row.r2_key);
  if (!obj) {
    // D1 row exists but R2 body is missing — orphan. Surface as 410 so the UI
    // can prune the listing without 5xx-style panic.
    return c.json({ error: "backup body missing from storage" }, 410);
  }
  // Use the live R2 object size so a stale catalog row can't cause clients to
  // truncate or hang. `obj.size` is set by R2 on PUT.
  const headers: Record<string, string> = {
    "content-type": "application/octet-stream",
    "content-disposition": `attachment; filename="${row.file_name}"`,
    "x-content-sha256": row.sha256,
    "Cache-Control": "no-store",
  };
  if (typeof obj.size === "number") {
    headers["content-length"] = String(obj.size);
  }
  return new Response(obj.body, { headers });
});

export default admin;