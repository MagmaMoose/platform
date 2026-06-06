-- SaaS product model (epic MagmaMoose/mikrotik-minder-pro#24): customer identity
-- + billing tables for the Stytch B2B + Stripe SaaS. Stytch owns authentication;
-- these tables are the product's own source of authorization + tenant truth.
-- Stytch / Stripe IDs are stored as EXTERNAL ids — never the sole source of authz
-- (which is always re-checked server-side against these rows).
--
-- Coexists with the existing email-based `tenant_members` (the Cloudflare Access /
-- superadmin path). Customer auth uses the user_id-based `tenant_memberships`
-- below. Backward compatible: nothing here is consulted until the Stytch auth
-- path is wired, so single-tenant / Access deploys are unaffected.

-- Customer org metadata, layered on the existing `tenants` foundation.
ALTER TABLE tenants ADD COLUMN slug TEXT;          -- URL-safe org handle (mirrors the Stytch org slug)
ALTER TABLE tenants ADD COLUMN deleted_at INTEGER; -- soft delete; NULL = active
ALTER TABLE tenants ADD COLUMN stytch_org_id TEXT; -- Stytch B2B organization_id this tenant maps to
CREATE UNIQUE INDEX tenants_slug_idx ON tenants(slug) WHERE slug IS NOT NULL;
CREATE UNIQUE INDEX tenants_stytch_org_idx ON tenants(stytch_org_id) WHERE stytch_org_id IS NOT NULL;

-- A human. Identity is federated (Stytch), but product authorization roots here.
CREATE TABLE users (
  id            TEXT PRIMARY KEY,
  primary_email TEXT NOT NULL UNIQUE,
  created_at    INTEGER NOT NULL,
  last_seen_at  INTEGER
);

-- Links an external auth identity (a Stytch member) to a local user. Several
-- providers / accounts can map to one user; the pair is the external key.
CREATE TABLE auth_accounts (
  provider         TEXT NOT NULL,        -- e.g. 'stytch'
  provider_user_id TEXT NOT NULL,        -- Stytch member_id
  user_id          TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at       INTEGER NOT NULL,
  PRIMARY KEY (provider, provider_user_id)
);
CREATE INDEX auth_accounts_user_idx ON auth_accounts(user_id);

-- user ↔ tenant membership with a role — the user_id-based model for customer
-- auth (distinct from the email-based `tenant_members` used by the Access path).
CREATE TABLE tenant_memberships (
  tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role       TEXT NOT NULL DEFAULT 'member',  -- 'owner' | 'admin' | 'member'
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, user_id)
);
CREATE INDEX tenant_memberships_user_idx ON tenant_memberships(user_id);

-- Stripe billing state, synced from Stripe webhooks and enforced server-side.
-- One billing account per tenant.
CREATE TABLE billing_accounts (
  tenant_id              TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  stripe_customer_id     TEXT,
  stripe_subscription_id TEXT,
  subscription_status    TEXT,     -- trialing | active | past_due | canceled | … (Stripe)
  plan                   TEXT,
  trial_ends_at          INTEGER,
  current_period_ends_at INTEGER,
  updated_at             INTEGER NOT NULL
);
CREATE INDEX billing_accounts_customer_idx ON billing_accounts(stripe_customer_id);
