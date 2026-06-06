-- Per-agent offsite git remote for the config-export history (drift detection).
-- The agent pushes its whole fleet's exports to one repo under per-device paths.
-- The token is stored SEALED (libsodium sealed-box to the agent's public key) —
-- the control plane only ever holds ciphertext, exactly like device credentials.
ALTER TABLE agents ADD COLUMN git_remote_url TEXT;
ALTER TABLE agents ADD COLUMN git_remote_branch TEXT;
ALTER TABLE agents ADD COLUMN git_remote_token_sealed TEXT;
