-- Command dispatch: the Pro UI enqueues commands; the agent polls and runs them.
-- The agent is otherwise push-only — this table, plus GET /v1/ingest/commands,
-- is the one channel the control plane uses to ask an agent to act.

CREATE TABLE commands (
  id            TEXT PRIMARY KEY,
  device_id     TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,          -- 'backup' | 'export' | 'update_apply' | 'sensitive_export'
  params        TEXT,                   -- JSON; command-specific options
  status        TEXT NOT NULL DEFAULT 'pending',  -- pending|claimed|succeeded|failed|expired
  scheduled_for INTEGER,                -- unix-seconds; NULL = run as soon as it's claimed
  requested_by  TEXT,                   -- operator email (Cf-Access) that enqueued it
  created_at    INTEGER NOT NULL,
  claimed_at    INTEGER,
  finished_at   INTEGER,
  result        TEXT,                   -- JSON result summary the agent reports back
  artifact      TEXT                    -- transient show-sensitive export body; purged on download
);
CREATE INDEX commands_device_idx ON commands(device_id, created_at DESC);
CREATE INDEX commands_claim_idx  ON commands(agent_id, status, created_at);
