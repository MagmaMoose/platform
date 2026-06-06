import type { Env } from "./env";
import { numEnv } from "./env";
import { nowSeconds } from "./ids";
import { fireAlert } from "./notify";

interface DeviceRow {
  id: string;
  agent_id: string;
  name: string;
  site: string | null;
  last_seen_at: number | null;
  heartbeat_interval_seconds: number | null;
  grace_seconds: number | null;
}

// Keep operator audit entries (Pro's audit_log) for 90 days, then prune — the
// table grows unbounded otherwise. Wrapped because the table only exists once
// Pro's migration 0009 is applied; on an OSS-only deploy this is a harmless no-op.
const AUDIT_RETENTION_SECONDS = 90 * 24 * 60 * 60;

async function pruneAuditLog(env: Env, now: number): Promise<void> {
  try {
    await env.DB.prepare("DELETE FROM audit_log WHERE created_at < ?1")
      .bind(now - AUDIT_RETENTION_SECONDS)
      .run();
  } catch {
    // audit_log not present (migration 0009 unapplied) — nothing to prune.
  }
}

export async function runScheduledSweep(env: Env, ctx: ExecutionContext): Promise<void> {
  const defaultInterval = numEnv(env.DEFAULT_HEARTBEAT_INTERVAL_SECONDS, 3600);
  // Grace can legitimately be 0 ("alert the moment we're past the interval").
  const defaultGrace = numEnv(env.DEFAULT_GRACE_SECONDS, 600, 0);
  const now = nowSeconds();

  // Housekeeping first, so a later early-return can't skip it.
  await pruneAuditLog(env, now);

  const { results } = await env.DB.prepare(
    `SELECT id, agent_id, name, site, last_seen_at, heartbeat_interval_seconds, grace_seconds
     FROM devices
     WHERE last_status != 'down' AND last_seen_at IS NOT NULL`,
  ).all<DeviceRow>();

  const stale = results.filter((d) => {
    const interval = d.heartbeat_interval_seconds ?? defaultInterval;
    const grace = d.grace_seconds ?? defaultGrace;
    return d.last_seen_at !== null && now - d.last_seen_at > interval + grace;
  });

  if (stale.length === 0) return;

  // Race guard: only flip to 'down' when last_seen_at hasn't moved since our
  // SELECT and the device isn't already 'down'. A heartbeat landing between
  // the SELECT and this UPDATE will bump last_seen_at and the WHERE clause
  // turns this into a no-op (meta.changes === 0), preventing the false alert.
  const lost: DeviceRow[] = [];
  for (const d of stale) {
    const res = await env.DB.prepare(
      `UPDATE devices SET last_status = 'down', last_status_changed_at = ?1
       WHERE id = ?2 AND last_seen_at = ?3 AND last_status != 'down'`,
    )
      .bind(now, d.id, d.last_seen_at)
      .run();
    if ((res.meta.changes ?? 0) > 0) {
      lost.push(d);
    }
  }

  if (lost.length === 0) return;

  await Promise.all(
    lost.map((d) => {
      const lastSeenAgo = d.last_seen_at ? now - d.last_seen_at : null;
      return fireAlert(
        env,
        {
          severity: "critical",
          kind: "heartbeat_missed",
          agent_id: d.agent_id,
          device_id: d.id,
          title: `${d.name} missed heartbeat`,
          payload: {
            device: d.name,
            site: d.site,
            last_seen_at: d.last_seen_at,
            last_seen_seconds_ago: lastSeenAgo,
            expected_interval_seconds: d.heartbeat_interval_seconds ?? defaultInterval,
            grace_seconds: d.grace_seconds ?? defaultGrace,
          },
        },
        ctx,
      );
    }),
  );
}
