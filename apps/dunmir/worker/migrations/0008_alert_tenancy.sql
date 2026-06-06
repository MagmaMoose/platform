-- Multi-tenancy phase 2a: alert isolation. alert_routes + alerts carry a
-- tenant_id so an alert is only ever delivered to its own tenant's destinations.
-- (Devices / commands / backups need no column — they scope via their agent_id.)
ALTER TABLE alert_routes ADD COLUMN tenant_id TEXT REFERENCES tenants(id);
ALTER TABLE alerts ADD COLUMN tenant_id TEXT REFERENCES tenants(id);

UPDATE alert_routes SET tenant_id = 'tnt_default' WHERE tenant_id IS NULL;
UPDATE alerts SET tenant_id = 'tnt_default' WHERE tenant_id IS NULL;

CREATE INDEX alert_routes_tenant_idx ON alert_routes(tenant_id);
