-- The agent's last observed egress IP (Cloudflare cf-connecting-ip on heartbeat).
-- Lets operators see exactly what source IP to allow through a router firewall
-- without shelling into the agent container.
ALTER TABLE agents ADD COLUMN last_ip TEXT;
