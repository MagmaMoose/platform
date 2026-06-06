# RFC: Control-plane-managed device config

**Status:** Draft · **Scope:** OSS worker + agent (this repo), with extension points for the proprietary Pro/SaaS layer.

## Problem

Today the agent's device list is *its own* config (a local file / Helm values). The control plane only stores device **metadata** (name, site, role, schedule), populated either by agent heartbeats or by the operator via `POST /v1/admin/devices`.

So "add a device in the UI" writes a metadata row that no agent is configured to act on — the device sits `unknown`/never-seen until someone *also* edits the agent's config and redeploys. The UI is not actually the control plane. For the licensed product that's the wrong shape.

We want the agent to be able to **fetch its config from the control plane**, so the UI becomes the source of truth — while the OSS worker + agent stay a complete, self-hostable product with **no proprietary code and no obligation to hand router credentials to the hosted plane**.

## Decision

Adopt an **open-core** split:

- The **OSS core** (this repo) gains a config-fetch *protocol* and a pluggable **`ConfigProvider`**. The default OSS provider serves device connection details with **credential *references*** — the secret never leaves the operator's environment.
- The **Pro/SaaS layer** (separate, private) implements a richer provider — a **credential vault** (envelope-encrypted to each agent), multi-tenancy, and licensing — by composing this worker, not forking it.

The agent is identical in both worlds; only the server-side provider differs.

## Goals / non-goals

**Goals**
- OSS remains fully functional standalone; existing deployments are unaffected (`config_source: local` stays the default).
- UI-driven device management works for self-hosters without shipping credentials to the backend.
- A clean extension seam the Pro layer clips onto with zero changes to the OSS core.

**Non-goals (for the OSS core)**
- Storing plaintext or recoverable router credentials in the control plane.
- Multi-tenancy, billing, licensing — these live in the Pro layer.

## The seam

### 1. Agent `config_source`

```yaml
# agent config (OSS)
config_source: local      # default — today's behaviour, devices defined locally
# or:
config_source: remote     # fetch the device list from the control plane each cycle
```

In `remote` mode the agent periodically `GET`s its config, merges it with any local `defaults`, and resolves credential references from its **local** environment. Connectivity, transport selection, and reporting are unchanged.

### 2. `GET /v1/ingest/config`

Authenticated by the agent token (same as the rest of `/v1/ingest/*`). Returns the devices assigned to the calling agent:

```json
{
  "version": 1,
  "generated_at": 1717200000,
  "defaults": { "heartbeat_interval_seconds": 300 },
  "devices": [
    {
      "name": "oci-rtr-01",
      "address": "193.123.39.172",
      "username": "minder",
      "transport": { "primary": "api", "fallback": "ssh" },
      "api_port": 8728, "use_tls": false, "ssh_port": 22,
      "site": "oci", "role": "lab",
      "heartbeat_interval_seconds": 300,
      "credential": { "kind": "ref", "password_env": "OCI_RTR_01_PASSWORD" }
    }
  ]
}
```

`credential.kind` is the seam:
- **`ref`** (OSS) — the agent reads `password_env` (or `ssh_key_path`) from its own environment. The backend stores only the *name*.
- **`sealed`** (Pro) — the response carries a ciphertext the agent decrypts locally (see *Pro extension*). Same protocol, same agent code path; the agent just decrypts when `kind == "sealed"`.

### 3. `ConfigProvider` (worker)

```ts
interface ConfigProvider {
  // Build the config doc for an authenticated agent.
  getConfig(env: Env, agentId: string): Promise<AgentConfigDoc>;
}
```

The OSS worker ships `RefConfigProvider` (reads connection details from D1, emits `credential.kind: "ref"`). The route handler depends only on the interface; the Pro layer injects a different provider at composition time.

## OSS implementation (refs)

### Schema

Additive columns on `devices` (all nullable — existing rows and the heartbeat auto-register path are unaffected):

```sql
ALTER TABLE devices ADD COLUMN address TEXT;
ALTER TABLE devices ADD COLUMN username TEXT;
ALTER TABLE devices ADD COLUMN password_env TEXT;     -- credential REFERENCE, not a secret
ALTER TABLE devices ADD COLUMN ssh_key_path TEXT;     -- reference
ALTER TABLE devices ADD COLUMN transport_primary TEXT;   -- 'api' | 'ssh'
ALTER TABLE devices ADD COLUMN transport_fallback TEXT;  -- 'api' | 'ssh' | null
ALTER TABLE devices ADD COLUMN api_port INTEGER;
ALTER TABLE devices ADD COLUMN use_tls INTEGER;       -- 0/1
ALTER TABLE devices ADD COLUMN ssh_port INTEGER;
```

No secret material is ever stored — only the *name* of an env var / key path the agent resolves locally.

`POST /v1/admin/devices` accepts these fields; `GET /v1/ingest/config` projects them into the doc above.

### Agent

`config_source: remote` adds a config loader that fetches the doc, maps each entry to the existing `DeviceConfig` (resolving `password_env` → `os.environ`), and feeds the daemon the same structure it builds from local YAML today. A fetch failure falls back to the last-known-good config so a control-plane blip never blanks the fleet.

This phase alone makes UI-driven device management real for self-hosters, with credentials staying in their cluster.

## Pro extension (contract only; internals live in the private repo)

The Pro layer is **not** described in full here — only how it attaches:

- **Provider injection.** A `VaultConfigProvider` implements `ConfigProvider` and emits `credential.kind: "sealed"`.
- **Envelope encryption.** At enrollment the agent registers a public key. The UI encrypts a router credential to that key; the backend stores only ciphertext; the agent decrypts locally. The hosted plane is therefore *not* a custodian of usable plaintext credentials — a deliberate liability/selling-point choice. (A simpler tenant-KMS variant where the backend decrypts transiently is possible but weaker.)
- **Multi-tenancy & licensing.** The OSS core keys everything by `agent_id`; the Pro layer adds an org→agent layer, row scoping, and a license tier that gates the vault/config-serving. OSS users never reach these.

### Composition on Cloudflare

Both options leave this repo's worker untouched:

1. **Open-core composition (recommended).** Publish this worker as a package exporting its Hono app + the `ConfigProvider` interface (default `RefConfigProvider`). The private Pro worker imports it, mounts proprietary routes (vault, tenant admin, licensing), injects `VaultConfigProvider`, and binds the same D1/R2. Deploy is the composed worker. No proxy hop.
2. **Service-binding wrapper.** A Pro worker sits in front with a service binding to the unmodified OSS worker; it owns config/vault/tenancy and forwards `/v1/ingest/*` + `/v1/admin/*`. Stronger isolation, slight proxy overhead.

Either way the SaaS reuses ingest / jobs / backups / alerts wholesale; the proprietary surface is just vault + tenancy + licensing.

## Security model

| | OSS (refs) | Pro (sealed) |
| --- | --- | --- |
| Secret at rest in control plane | none (only a ref name) | ciphertext only (enveloped to agent key) |
| Plane can read a router credential | no | no (zero-knowledge variant) / transiently (KMS variant) |
| Transport | TLS + agent-token bearer | same |
| Blast radius if D1 leaks | env-var names | ciphertext useless without agent keys |

## Phased plan

| Phase | Repo | Content |
| --- | --- | --- |
| **1** | OSS | `devices` connection columns + admin acceptance · `GET /v1/ingest/config` (refs) · agent `config_source: remote` with last-known-good fallback. **Unblocks UI device-add.** |
| **2** | OSS | Agent keypair enrollment so the protocol can carry `sealed` credentials (OSS still emits `ref`). |
| **3** | Pro (private) | `VaultConfigProvider` + envelope crypto, injected via composition. |
| **4** | Pro (private) | Multi-tenant org model, licensing gates, UI credential entry. |

## Backwards compatibility

`config_source` defaults to `local`; agents and operators that never opt in see no change. The new `devices` columns are nullable and ignored by the existing heartbeat/admin paths. `GET /v1/ingest/config` is additive.

## Open questions

- Config refresh cadence in `remote` mode — piggyback the heartbeat interval, or a dedicated `config_interval`?
- Reconciliation when a device is removed from the control plane while the agent holds it — drain vs. drop.
- Whether `defaults` (intervals, transport) should also be control-plane-managed or stay agent-local in OSS.
