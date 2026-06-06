-- Multi-tenancy foundation. Tenant scoping roots at agents.tenant_id; other
-- entities (devices, jobs, commands, backups, alert routes) scope via the owning
-- agent or gain their own tenant_id in later phases.
--
-- Backward compatible: a single 'tnt_default' tenant owns all existing agents,
-- and with the MULTI_TENANT flag off the worker always resolves to it — so
-- single-tenant / self-hosted deployments behave exactly as before.

CREATE TABLE tenants (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

-- Maps a Cloudflare-Access-authenticated operator email to its tenant. Only
-- consulted when MULTI_TENANT is on.
CREATE TABLE tenant_members (
  email      TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL
);
CREATE INDEX tenant_members_tenant_idx ON tenant_members(tenant_id);

ALTER TABLE agents ADD COLUMN tenant_id TEXT REFERENCES tenants(id);

-- Default tenant owns every pre-existing agent.
INSERT INTO tenants (id, name, created_at)
  VALUES ('tnt_default', 'Default', CAST(strftime('%s', 'now') AS INTEGER));
UPDATE agents SET tenant_id = 'tnt_default' WHERE tenant_id IS NULL;

CREATE INDEX agents_tenant_idx ON agents(tenant_id);
