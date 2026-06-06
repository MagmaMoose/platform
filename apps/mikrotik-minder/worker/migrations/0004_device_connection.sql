-- Control-plane-managed device config (RFC: docs/rfc-control-plane-managed-config.md), phase 1.
--
-- Connection details so the control plane can serve an agent its device config
-- (GET /v1/ingest/config). All columns are nullable and additive: existing rows,
-- the heartbeat auto-register path, and admin upserts that omit them are
-- unaffected. Credentials are stored ONLY as references (an env-var name or a
-- key path the agent resolves locally) — never as secrets.

ALTER TABLE devices ADD COLUMN address TEXT;
ALTER TABLE devices ADD COLUMN username TEXT;
ALTER TABLE devices ADD COLUMN password_env TEXT;        -- reference, not a secret
ALTER TABLE devices ADD COLUMN ssh_key_path TEXT;        -- reference, not a secret
ALTER TABLE devices ADD COLUMN transport_primary TEXT;   -- 'api' | 'ssh'
ALTER TABLE devices ADD COLUMN transport_fallback TEXT;  -- 'api' | 'ssh' | null
ALTER TABLE devices ADD COLUMN api_port INTEGER;
ALTER TABLE devices ADD COLUMN use_tls INTEGER;          -- 0 / 1
ALTER TABLE devices ADD COLUMN ssh_port INTEGER;
