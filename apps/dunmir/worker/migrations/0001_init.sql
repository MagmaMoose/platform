-- Mikrotik Minder control-plane schema.
-- All timestamps are unix-seconds (INTEGER) so the worker can compute deltas without parsing.

CREATE TABLE agents (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,
  token_hash   TEXT NOT NULL UNIQUE,
  created_at   INTEGER NOT NULL,
  last_seen_at INTEGER,
  disabled     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE devices (
  id                          TEXT PRIMARY KEY,
  agent_id                    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  name                        TEXT NOT NULL,
  site                        TEXT,
  role                        TEXT,
  tags                        TEXT,
  heartbeat_interval_seconds  INTEGER,
  grace_seconds               INTEGER,
  last_seen_at                INTEGER,
  last_status                 TEXT NOT NULL DEFAULT 'unknown',
  last_status_changed_at      INTEGER,
  created_at                  INTEGER NOT NULL,
  UNIQUE (agent_id, name)
);
CREATE INDEX devices_status_idx ON devices(last_status);
CREATE INDEX devices_last_seen_idx ON devices(last_seen_at);

CREATE TABLE jobs (
  id           TEXT PRIMARY KEY,
  agent_id     TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  device_id    TEXT REFERENCES devices(id) ON DELETE SET NULL,
  kind         TEXT NOT NULL,
  status       TEXT NOT NULL,
  started_at   INTEGER NOT NULL,
  finished_at  INTEGER NOT NULL,
  summary      TEXT,
  details      TEXT,
  created_at   INTEGER NOT NULL
);
CREATE INDEX jobs_device_idx     ON jobs(device_id, finished_at DESC);
CREATE INDEX jobs_status_idx     ON jobs(status, finished_at DESC);
CREATE INDEX jobs_finished_idx   ON jobs(finished_at DESC);

CREATE TABLE alert_routes (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  kind          TEXT NOT NULL,          -- 'webhook' | 'slack' | 'discord'
  url           TEXT NOT NULL,
  events        TEXT,                   -- JSON array of alert kinds; NULL = all
  min_severity  TEXT NOT NULL DEFAULT 'warning',
  enabled       INTEGER NOT NULL DEFAULT 1,
  created_at    INTEGER NOT NULL
);

CREATE TABLE alerts (
  id            TEXT PRIMARY KEY,
  severity      TEXT NOT NULL,          -- 'info' | 'warning' | 'critical'
  kind          TEXT NOT NULL,          -- 'heartbeat_missed' | 'heartbeat_recovered' | 'job_failed' | ...
  agent_id      TEXT REFERENCES agents(id) ON DELETE SET NULL,
  device_id     TEXT REFERENCES devices(id) ON DELETE SET NULL,
  job_id        TEXT REFERENCES jobs(id) ON DELETE SET NULL,
  title         TEXT NOT NULL,
  payload       TEXT NOT NULL,          -- JSON
  created_at    INTEGER NOT NULL
);
CREATE INDEX alerts_created_idx ON alerts(created_at DESC);
CREATE INDEX alerts_device_idx  ON alerts(device_id, created_at DESC);

CREATE TABLE alert_deliveries (
  id            TEXT PRIMARY KEY,
  alert_id      TEXT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  route_id      TEXT NOT NULL REFERENCES alert_routes(id) ON DELETE CASCADE,
  status        TEXT NOT NULL,          -- 'ok' | 'failed'
  http_status   INTEGER,
  error         TEXT,
  delivered_at  INTEGER NOT NULL
);
CREATE INDEX alert_deliveries_alert_idx ON alert_deliveries(alert_id);
