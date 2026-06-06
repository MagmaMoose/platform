-- Backup catalog: one row per encrypted backup the agent uploads to R2.
-- The agent still keeps a 14-day local copy on its PVC (unchanged); this table
-- is what the Pro UI queries for the "Backups" tab + the download endpoint.
--
-- The body never lives in D1 — D1 stores only the R2 key, sha256, size, and
-- timestamps. The download endpoint streams straight from R2 to the operator.

CREATE TABLE backup_files (
  id          TEXT PRIMARY KEY,
  agent_id    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  device_id   TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  file_name   TEXT NOT NULL,          -- e.g. minder-oci-rtr-01-20260523T070200Z.backup
  r2_key      TEXT NOT NULL UNIQUE,   -- backups/<device_id>/<file_name>
  size_bytes  INTEGER NOT NULL,
  sha256      TEXT NOT NULL,          -- of the encrypted body, matches the agent's local copy
  created_at  INTEGER NOT NULL        -- unix-seconds; when the upload completed
);

-- Pro UI lists "backups for this device, most recent first".
CREATE INDEX backup_files_device_idx ON backup_files(device_id, created_at DESC);

-- An agent's retention sweep deletes its local + control-plane catalog rows;
-- supports `WHERE agent_id = ? AND device_id = ? ORDER BY created_at`.
CREATE INDEX backup_files_agent_idx ON backup_files(agent_id, device_id, created_at DESC);
