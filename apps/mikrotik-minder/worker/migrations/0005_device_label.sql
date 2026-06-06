-- Operator-facing display label. The device's `name` stays the immutable agent
-- match-key (heartbeats/jobs/config all key on it); `label` is just what the UI
-- shows, so a device can be "renamed" without breaking matching. Nullable +
-- additive — the UI falls back to `name` when it's unset.
ALTER TABLE devices ADD COLUMN label TEXT;
