-- Operator audit log. Written by the Pro UI's request hook (Pro repo:
-- src/hooks.server.ts) on every Cloudflare-Access-authenticated operator action
-- — page views, command enqueues, and artifact/backup downloads. Unauthenticated
-- traffic (health checks, uptime probes, scanners) carries no Access identity and
-- is never recorded, so this is operators only. The OSS worker does not write
-- here; the table lives in the shared `minder` schema because the Pro app binds
-- the same D1 and there is one migration chain.

CREATE TABLE audit_log (
  id            TEXT PRIMARY KEY,
  actor_email   TEXT,                  -- Cf-Access-Authenticated-User-Email (who)
  actor_ip      TEXT,                  -- CF-Connecting-IP (from where)
  actor_country TEXT,                  -- CF-IPCountry, best-effort
  action        TEXT NOT NULL,         -- view_dashboard|view_device|view_config|enqueue_command|download_backup|download_sensitive_export|view_audit_log
  method        TEXT NOT NULL,         -- HTTP method
  path          TEXT NOT NULL,         -- request path (what)
  route_id      TEXT,                  -- SvelteKit route id the request resolved to
  target_kind   TEXT,                  -- 'device' | 'command' | 'backup' | NULL
  target_id     TEXT,                  -- device / command / backup id, when applicable
  status        INTEGER,               -- HTTP response status
  created_at    INTEGER NOT NULL       -- unix-seconds (when)
);
CREATE INDEX audit_log_created_idx ON audit_log(created_at DESC);
CREATE INDEX audit_log_actor_idx   ON audit_log(actor_email, created_at DESC);
