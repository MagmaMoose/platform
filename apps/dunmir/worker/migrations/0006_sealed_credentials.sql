-- Pro vault plumbing (open-core). The OSS worker stays a DUMB PIPE: it stores
-- and serves opaque blobs, holding no crypto and no plaintext.
--
--   agents.public_key         — the agent's Curve25519 public key (libsodium
--                               sealed-box), registered via POST /v1/ingest/agent-key.
--   devices.credential_sealed — a sealed-box ciphertext the agent decrypts
--                               locally with its private key; set by the licensed
--                               UI after it encrypts to the agent's public key.
--                               When present, GET /v1/ingest/config serves
--                               credential.kind = "sealed" instead of "ref".
ALTER TABLE agents ADD COLUMN public_key TEXT;
ALTER TABLE devices ADD COLUMN credential_sealed TEXT;
