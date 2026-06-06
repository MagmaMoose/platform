# CHANGELOG

<!-- version list -->

## v1.25.0 (2026-06-03)

### Bug Fixes

- **agent**: Keep SSH auth-failure messages accurate for key auth
  ([`3ce1e53`](https://github.com/MagmaMoose/dunmir/commit/3ce1e53ecd6d1e0399aa874096b5e1b04aa1237c))

### Features

- **agent**: Explain SSH auth failures (method vs secret)
  ([`3f72815`](https://github.com/MagmaMoose/dunmir/commit/3f7281545376dbd49dbe225d477051a7c411cf1a))


## v1.24.0 (2026-06-03)

### Bug Fixes

- **agent**: Address review on the device-onboarding changes
  ([`e7f2b2e`](https://github.com/MagmaMoose/dunmir/commit/e7f2b2e6d1382fdd0b51225e40929a96d2cb3e6a))

- **agent**: Degrade gracefully when the managed state dir isn't writable
  ([`3bd23ba`](https://github.com/MagmaMoose/dunmir/commit/3bd23ba9ff6eb6ec690d2ad46a0780a7970ba36c))

- **worker**: Git-remote endpoint — explicit clears + https-only
  ([`3d9e293`](https://github.com/MagmaMoose/dunmir/commit/3d9e2936e08bb3304f0bb7445eb54dce30f071ad))

### Features

- **agent**: Apply the control-plane's per-agent offsite git remote
  ([`39845a0`](https://github.com/MagmaMoose/dunmir/commit/39845a0d8d69ca36dabdd952f73971107f65079f))

- **agent**: Zero-config pipelines, dual-transport probe, RouterBOARD over API
  ([`a252097`](https://github.com/MagmaMoose/dunmir/commit/a252097cee96d39121c6c6d456dd80e735b47e74))

- **worker**: Per-agent git remote for config-export history
  ([`5e473a1`](https://github.com/MagmaMoose/dunmir/commit/5e473a17724f2ad5adbb0c04e8e13d5dced06ab4))


## v1.23.0 (2026-06-03)

### Features

- **agent**: Report RouterOS version + board over API (no SSH needed)
  ([`77e6274`](https://github.com/MagmaMoose/dunmir/commit/77e62743cbee8491b97511eb20b0e7d0ee1c610d))


## v1.22.0 (2026-06-03)

### Features

- **agent**: Log the winning transport + RouterOS version on success
  ([`42d1506`](https://github.com/MagmaMoose/dunmir/commit/42d15066d8f19e79a40b909f3f00e6f9539e4b9e))


## v1.21.2 (2026-06-03)

### Bug Fixes

- **worker**: Device edit keeps omitted fields (COALESCE), no clobber
  ([`4897603`](https://github.com/MagmaMoose/dunmir/commit/48976034599bef36ee62ed40f38fffb35fc4bdc9))


## v1.21.1 (2026-06-03)

### Bug Fixes

- **worker**: Stamp agent egress IP on every contact, not just heartbeat
  ([`9c404a5`](https://github.com/MagmaMoose/dunmir/commit/9c404a58c6f48e1c8387d7203f510144c653c206))


## v1.21.0 (2026-06-03)

### Features

- **worker**: Record the agent's egress IP on heartbeat
  ([`872aa06`](https://github.com/MagmaMoose/dunmir/commit/872aa0614fbba71b5a496baa2d304c889bf36a6a))


## v1.20.1 (2026-06-03)

### Bug Fixes

- **agent**: SSH banner/auth (+ API login) timeouts too short for RouterOS
  ([`c582d83`](https://github.com/MagmaMoose/dunmir/commit/c582d8315cf13cb1e7142299b1149b1bbda6b8aa))


## v1.20.0 (2026-06-02)

### Features

- **worker**: Delete-agent + reassign-device admin endpoints
  ([`ddfbf7f`](https://github.com/MagmaMoose/dunmir/commit/ddfbf7ffa3c7d754b9c4be2b22489664450593a7))


## v1.19.4 (2026-06-02)

### Bug Fixes

- **worker**: Mark agents seen on any contact, not just heartbeats
  ([`2ed5275`](https://github.com/MagmaMoose/dunmir/commit/2ed5275b50b32d57b57827e282a8a7b9febc2969))

### Continuous Integration

- **agent**: Publish the agent image as dunmir-agent
  ([`e7a3720`](https://github.com/MagmaMoose/dunmir/commit/e7a3720cb44ea9ca3f4a3b41c8598b632fa85446))


## v1.19.3 (2026-06-02)

### Bug Fixes

- **worker**: Deploy prod to the 'dunmir' worker, not 'mikrotik-minder'
  ([`b0737f7`](https://github.com/MagmaMoose/dunmir/commit/b0737f7235bd5520b5b37c9650c3e9823d45b0de))


## v1.19.2 (2026-06-02)

### Bug Fixes

- **worker**: Correct prod Stytch JWKS URL to the B2B endpoint
  ([`37b3a1f`](https://github.com/MagmaMoose/dunmir/commit/37b3a1f9d1c36f286fb7d99535d168d5ca354deb))


## v1.19.1 (2026-06-02)

### Bug Fixes

- **worker**: Read organization_id from the Stytch B2B org claim
  ([`bd75b9a`](https://github.com/MagmaMoose/dunmir/commit/bd75b9aa605465a1582fcd4a82b55af1693a6411))

### Documentation

- **worker**: Correct pickEmail doc to reflect direct claim fallback
  ([`e6524c3`](https://github.com/MagmaMoose/dunmir/commit/e6524c3257e33066f01957dbed17cb0db52c3eb4))


## v1.19.0 (2026-06-02)

### Features

- **worker**: JIT-provision a tenant for a new Stytch org (self-serve onboarding)
  ([`aa8911d`](https://github.com/MagmaMoose/dunmir/commit/aa8911d1e1408d2936792a336807df37856bafe8))


## v1.18.0 (2026-06-01)

### Features

- **worker**: Accept customer Stytch sessions on /v1/admin/* (cutover)
  ([#52](https://github.com/MagmaMoose/dunmir/pull/52),
  [`64b48d5`](https://github.com/MagmaMoose/dunmir/commit/64b48d5ce981f11a2e47a55d19388648b3044033))


## v1.17.0 (2026-06-01)

### Bug Fixes

- **stytch**: Ensure tenant_memberships row exists for existing users
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))

- **stytch**: Normalize email before upsert to avoid duplicate users on case/whitespace differences
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))

- **worker**: Restrict JWT verification to RS256 algorithm
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))

- **worker**: Validate Stytch JWTs with Web Crypto, drop jose (fixes CI)
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))

### Features

- **worker**: Add tenants.stytch_org_id for the Stytch org→tenant map
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))

- **worker**: SaaS product-model migration (0010)
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))

- **worker**: SaaS product-model migration (0010) — users / memberships / billing
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))

- **worker**: Stytch B2B session validation (SaaS Phase 1 §4)
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))

- **worker**: Stytch B2B session validation for customer auth
  ([#50](https://github.com/MagmaMoose/dunmir/pull/50),
  [`fde66c1`](https://github.com/MagmaMoose/dunmir/commit/fde66c1998da0c277648a5f64c1a493393a884e6))


## v1.16.0 (2026-06-01)

### Bug Fixes

- **agent**: Register vault public key whenever agent_key_path is set
  ([#49](https://github.com/MagmaMoose/mikrotik-minder/pull/49),
  [`0cf6a33`](https://github.com/MagmaMoose/mikrotik-minder/commit/0cf6a330b626ad6cae07ad2cd5cd0454f3163107))

### Features

- **worker**: Audit_log table for the Pro operator audit log (migration 0009)
  ([#49](https://github.com/MagmaMoose/mikrotik-minder/pull/49),
  [`0cf6a33`](https://github.com/MagmaMoose/mikrotik-minder/commit/0cf6a330b626ad6cae07ad2cd5cd0454f3163107))

- **worker**: Prune Pro audit_log after 90 days in the scheduled sweep
  ([#49](https://github.com/MagmaMoose/mikrotik-minder/pull/49),
  [`0cf6a33`](https://github.com/MagmaMoose/mikrotik-minder/commit/0cf6a330b626ad6cae07ad2cd5cd0454f3163107))

### Testing

- **worker**: Cross-tenant isolation suite + sensitive-export artifact purge fix (multi-tenancy
  phase 4) ([#43](https://github.com/MagmaMoose/mikrotik-minder/pull/43),
  [`df04ca3`](https://github.com/MagmaMoose/mikrotik-minder/commit/df04ca328d69204849c649fd89319fd4a7d15ffc))


## v1.15.0 (2026-06-01)

### Features

- **worker**: Superadmin tenant-lifecycle endpoints (multi-tenancy phase 3a)
  ([#42](https://github.com/MagmaMoose/mikrotik-minder/pull/42),
  [`c530de7`](https://github.com/MagmaMoose/mikrotik-minder/commit/c530de7ed65c913fa6a8bf14040a303611699557))


## v1.14.0 (2026-06-01)

### Features

- **worker**: Tenant-isolate alerts (multi-tenancy phase 2a)
  ([#40](https://github.com/MagmaMoose/mikrotik-minder/pull/40),
  [`d77cad9`](https://github.com/MagmaMoose/mikrotik-minder/commit/d77cad96edf7d0df1192f57b29df1eae2d488e86))

- **worker**: Tenant-scope devices/commands/backups (multi-tenancy phase 2b)
  ([#41](https://github.com/MagmaMoose/mikrotik-minder/pull/41),
  [`d147a5f`](https://github.com/MagmaMoose/mikrotik-minder/commit/d147a5f8197aec27e0ccf4a119d844087b961986))


## v1.13.0 (2026-05-31)

### Features

- **worker**: Multi-tenancy foundation — tenant model + scoped agents (phase 1)
  ([#39](https://github.com/MagmaMoose/mikrotik-minder/pull/39),
  [`0918628`](https://github.com/MagmaMoose/mikrotik-minder/commit/0918628ad78fffcf8893f6bb5fd8ce0c5d221a7d))

- **worker**: Sealed-credential + agent-key plumbing for the Pro vault
  ([#37](https://github.com/MagmaMoose/mikrotik-minder/pull/37),
  [`0fa4878`](https://github.com/MagmaMoose/mikrotik-minder/commit/0fa4878c974b3218c5f44ba2c7f2eda4de94a9b8))


## v1.12.0 (2026-05-31)

### Features

- **agent**: Sealed-credential support (vault keypair + decrypt)
  ([#38](https://github.com/MagmaMoose/mikrotik-minder/pull/38),
  [`bb0cc0f`](https://github.com/MagmaMoose/mikrotik-minder/commit/bb0cc0f4c0135189755b5aa51a7a01c84bfa0433))


## v1.11.0 (2026-05-31)

### Features

- **agent**: Periodic remote-config refresh
  ([#36](https://github.com/MagmaMoose/mikrotik-minder/pull/36),
  [`e2f5a97`](https://github.com/MagmaMoose/mikrotik-minder/commit/e2f5a97c69c2e3a298b47aa141728b40e5b00cf7))


## v1.10.0 (2026-05-31)

### Features

- **worker**: Device display label (migration 0005 + admin upsert)
  ([#35](https://github.com/MagmaMoose/mikrotik-minder/pull/35),
  [`c7cacd3`](https://github.com/MagmaMoose/mikrotik-minder/commit/c7cacd3fbd243ef5e7cb13c29dfa4496e360c03b))


## v1.9.0 (2026-05-31)

### Features

- **agent**: Config_source: remote — fetch device config from control plane
  ([#34](https://github.com/MagmaMoose/mikrotik-minder/pull/34),
  [`ecd6d6f`](https://github.com/MagmaMoose/mikrotik-minder/commit/ecd6d6f272fbc322303311aaf67a8e6a94f3591a))


## v1.8.0 (2026-05-31)

### Documentation

- RFC for control-plane-managed device config (open-core)
  ([#31](https://github.com/MagmaMoose/mikrotik-minder/pull/31),
  [`0b6318e`](https://github.com/MagmaMoose/mikrotik-minder/commit/0b6318e59e755e52d355de4154767fe99551877f))

### Features

- **worker**: Device connection fields + GET /v1/ingest/config (RFC phase 1)
  ([#33](https://github.com/MagmaMoose/mikrotik-minder/pull/33),
  [`00756f3`](https://github.com/MagmaMoose/mikrotik-minder/commit/00756f37b44cadf12feda174889686ff644d08d6))


## v1.7.0 (2026-05-31)

### Features

- **agent**: Report device address + identity in inventory_sync
  ([#32](https://github.com/MagmaMoose/mikrotik-minder/pull/32),
  [`1ccc353`](https://github.com/MagmaMoose/mikrotik-minder/commit/1ccc353bb30ca55154107c56dd81d9b577340615))


## v1.6.0 (2026-05-31)

### Build System

- **deps**: Bump docker/login-action from 3.7.0 to 4.2.0
  ([#26](https://github.com/MagmaMoose/mikrotik-minder/pull/26),
  [`32be553`](https://github.com/MagmaMoose/mikrotik-minder/commit/32be5535fcab9c80458998e7cd993891a559dfb7))

- **deps**: Bump docker/metadata-action from 5.10.0 to 6.1.0
  ([#24](https://github.com/MagmaMoose/mikrotik-minder/pull/24),
  [`516c811`](https://github.com/MagmaMoose/mikrotik-minder/commit/516c811c03059e7d7872dab0713136b6de71175e))

- **deps**: Bump docker/setup-buildx-action from 3.12.0 to 4.1.0
  ([#22](https://github.com/MagmaMoose/mikrotik-minder/pull/22),
  [`b2f2081`](https://github.com/MagmaMoose/mikrotik-minder/commit/b2f2081cf1fdc695ed9488c6ee06ef74f3781f31))

- **deps**: Bump docker/setup-qemu-action from 4.0.0 to 4.1.0
  ([#25](https://github.com/MagmaMoose/mikrotik-minder/pull/25),
  [`50a68b4`](https://github.com/MagmaMoose/mikrotik-minder/commit/50a68b458e1315f8e47bb2c2f3ad14d34f7a1c09))

- **deps**: Bump hono from 4.12.21 to 4.12.23 in /worker
  ([#18](https://github.com/MagmaMoose/mikrotik-minder/pull/18),
  [`4a71b78`](https://github.com/MagmaMoose/mikrotik-minder/commit/4a71b78e5f7a6c82f2a6aa992e8d62302f1db9e9))

- **deps**: Bump magmamoose/release-runner from 1.14.1 to 1.22.0
  ([#23](https://github.com/MagmaMoose/mikrotik-minder/pull/23),
  [`ad0332b`](https://github.com/MagmaMoose/mikrotik-minder/commit/ad0332ba4ac7963c4168a1480d43ac89b9365a5b))

- **deps-dev**: Bump @cloudflare/workers-types in /worker
  ([#19](https://github.com/MagmaMoose/mikrotik-minder/pull/19),
  [`0996c44`](https://github.com/MagmaMoose/mikrotik-minder/commit/0996c44cbc0234ae06c661482bd0d402281770d9))

- **deps-dev**: Bump typescript from 5.9.3 to 6.0.3 in /worker
  ([#20](https://github.com/MagmaMoose/mikrotik-minder/pull/20),
  [`3d60f72`](https://github.com/MagmaMoose/mikrotik-minder/commit/3d60f726259f1f5f538d08a339526d33377a9e6b))

- **deps-dev**: Bump wrangler from 4.93.0 to 4.95.0 in /worker
  ([#21](https://github.com/MagmaMoose/mikrotik-minder/pull/21),
  [`c6492bb`](https://github.com/MagmaMoose/mikrotik-minder/commit/c6492bbb4c11babe62678853bebcda33463c3465))

### Chores

- **worker**: Point PRO_UI_URL at https://dunmir.magmamoose.com
  ([#29](https://github.com/MagmaMoose/mikrotik-minder/pull/29),
  [`59eb90f`](https://github.com/MagmaMoose/mikrotik-minder/commit/59eb90f3e49bfa53b34b2cd885f594dc71444b33))

### Features

- **agent**: Device inventory probe (CHR/licence/cloud) + packet-loss ping
  ([#30](https://github.com/MagmaMoose/mikrotik-minder/pull/30),
  [`ef61a1f`](https://github.com/MagmaMoose/mikrotik-minder/commit/ef61a1fb49e1b70445f0fc61eee2871b0f35a991))


## v1.5.2 (2026-05-30)

### Bug Fixes

- **agent**: Harden SSH errors, host-key verification, and false-alert paths
  ([#28](https://github.com/MagmaMoose/mikrotik-minder/pull/28),
  [`a4d808e`](https://github.com/MagmaMoose/mikrotik-minder/commit/a4d808e1adb3ca3958ec064fb8872ea339f77770))

- **agent**: Use a custom TOFU host-key policy instead of paramiko.AutoAddPolicy
  ([#28](https://github.com/MagmaMoose/mikrotik-minder/pull/28),
  [`a4d808e`](https://github.com/MagmaMoose/mikrotik-minder/commit/a4d808e1adb3ca3958ec064fb8872ea339f77770))


## v1.5.1 (2026-05-29)

### Bug Fixes

- **agent**: Serialise shared git repo and stagger device startup
  ([#27](https://github.com/MagmaMoose/mikrotik-minder/pull/27),
  [`495a770`](https://github.com/MagmaMoose/mikrotik-minder/commit/495a770732b8726f28281eb6088cdba0c24bab12))

### Build System

- **deps**: Bump actions/checkout from 4.3.1 to 6.0.2
  ([#7](https://github.com/MagmaMoose/mikrotik-minder/pull/7),
  [`20d31fc`](https://github.com/MagmaMoose/mikrotik-minder/commit/20d31fc427ea118be0d9764a9b9fe74649855a48))

- **deps**: Bump cloudflare/wrangler-action from 3.15.0 to 4.0.0
  ([#10](https://github.com/MagmaMoose/mikrotik-minder/pull/10),
  [`4680ff5`](https://github.com/MagmaMoose/mikrotik-minder/commit/4680ff5433ddc3ba00db41a6ec14811b0c2d574b))

- **deps**: Bump docker/build-push-action from 6.19.2 to 7.2.0
  ([#9](https://github.com/MagmaMoose/mikrotik-minder/pull/9),
  [`b8e30f9`](https://github.com/MagmaMoose/mikrotik-minder/commit/b8e30f95f0b4335357367a06bcf3d58d14fff0dc))

- **deps**: Bump docker/setup-qemu-action from 3.7.0 to 4.0.0
  ([#8](https://github.com/MagmaMoose/mikrotik-minder/pull/8),
  [`190e47c`](https://github.com/MagmaMoose/mikrotik-minder/commit/190e47c837b4b723bc099b4d29de550c60bfb3f1))

- **deps**: Bump the npm_and_yarn group across 1 directory with 2 updates
  ([#4](https://github.com/MagmaMoose/mikrotik-minder/pull/4),
  [`9e23f7c`](https://github.com/MagmaMoose/mikrotik-minder/commit/9e23f7c2b24412916eb6dd4165db4e1e303d825a))

### Continuous Integration

- Move runners to Node 24 and finish action deprecation cleanup
  ([#17](https://github.com/MagmaMoose/mikrotik-minder/pull/17),
  [`570423b`](https://github.com/MagmaMoose/mikrotik-minder/commit/570423b7c69d85b46f5d05887e42bd3d7f411b83))


## v1.5.0 (2026-05-23)

### Bug Fixes

- **admin**: Add anti-caching headers to artifact download endpoint
  ([`437a766`](https://github.com/MagmaMoose/mikrotik-minder/commit/437a766e00fee565eacc019631ee9c78ffb0e7b0))

- **admin**: Derive requested_by from authenticated user instead of request body
  ([`a4c125c`](https://github.com/MagmaMoose/mikrotik-minder/commit/a4c125cacf1fde04069221877c124a4a5d5dd1c1))

- **admin**: Make artifact download atomic with UPDATE ... RETURNING
  ([`5d6f998`](https://github.com/MagmaMoose/mikrotik-minder/commit/5d6f998607c1b1c498dc0e0f2b91bcb041313a13))

- **admin**: Populate requested_by from X-Auth-Email header
  ([`83ceff7`](https://github.com/MagmaMoose/mikrotik-minder/commit/83ceff7cf65558b00b5a417a92208cf098dae45d))

- **admin**: Return pre-update artifact in one-shot download endpoint
  ([`5669bdd`](https://github.com/MagmaMoose/mikrotik-minder/commit/5669bdd17ed56c010d554a8b46c6ac6a83577d7d))

- **admin**: Validate X-Auth-Email header for commands endpoint
  ([`f0d11fa`](https://github.com/MagmaMoose/mikrotik-minder/commit/f0d11fa3dfa95794f2f1b5d9ded7faca2eea2a1e))

- **agent**: Align sensitive export docstring with CRLF normalization
  ([`4024100`](https://github.com/MagmaMoose/mikrotik-minder/commit/4024100df6150b82b8ff949763ee8a19c3017de7))

- **agent**: Enforce artifact size limit in sensitive export command
  ([`5ed94b7`](https://github.com/MagmaMoose/mikrotik-minder/commit/5ed94b7dad5aef47ae632e6d93959ecd6214314e))

- **agent**: Report command results for export/backup commands
  ([`8d47efb`](https://github.com/MagmaMoose/mikrotik-minder/commit/8d47efb6dc224a750d7811704ece018527820cfc))

- **agent**: Satisfy ruff (unused noqa + line length)
  ([`aefd605`](https://github.com/MagmaMoose/mikrotik-minder/commit/aefd6058b1dbfeaa3013c29fdce437081ec5177d))

- **agent**: Stream backup upload and URL-encode device/name
  ([`059f3b5`](https://github.com/MagmaMoose/mikrotik-minder/commit/059f3b52bcb1104c6f3789c036709210e3b13dff))

- **agent**: Wrap E501 in sensitive export size-limit message
  ([`ada14d8`](https://github.com/MagmaMoose/mikrotik-minder/commit/ada14d8084ae6d96bce77c2178efb869e237fe68))

- **agent**: Wrap long MinderError lines added by status_code refactor
  ([`f1965a6`](https://github.com/MagmaMoose/mikrotik-minder/commit/f1965a6619b1ccca5e89240fe08404518b312911))

- **commands**: Restrict artifact to sensitive_export kind + add agent tests
  ([`db9861d`](https://github.com/MagmaMoose/mikrotik-minder/commit/db9861d6128ce8b2911818546207517e9ddc4395))

- **daemon**: Accept CommandRef in _execute_command_via_daemon
  ([`f1f8c54`](https://github.com/MagmaMoose/mikrotik-minder/commit/f1f8c54d00a74bf08e29eec2fdabce292a5f23db))

- **daemon**: Only update last_backup on successful backup command
  ([`0fc8574`](https://github.com/MagmaMoose/mikrotik-minder/commit/0fc857440ac3ebcac33a70a1a17b143cb8dfd58c))

- **daemon**: Update device timestamps after command execution
  ([`d6fe667`](https://github.com/MagmaMoose/mikrotik-minder/commit/d6fe667de3062c4be42603187319c86261a3d30a))

- **ingest**: Fix invalid SQL in command claim query
  ([`4d4ea7f`](https://github.com/MagmaMoose/mikrotik-minder/commit/4d4ea7fa153fb6fbaae5e1ffd3f2ce952741c015))

- **ingest**: Handle concurrent backup upload race with upsert
  ([`7bfa5e6`](https://github.com/MagmaMoose/mikrotik-minder/commit/7bfa5e6657bbc105803c6185afc9e9600622252e))

- **ingest**: Preserve artifact payload verbatim without trimming
  ([`98df997`](https://github.com/MagmaMoose/mikrotik-minder/commit/98df99707b94a310a27fd82757408cc5f8379812))

- **ingest**: Verify sha256 on backup dedupe to prevent silent overwrite
  ([`b452e1c`](https://github.com/MagmaMoose/mikrotik-minder/commit/b452e1c4e55e1139de780506b85835331a7894a5))

- **migrations**: Add device_id to backup_files_agent_idx
  ([`88e9833`](https://github.com/MagmaMoose/mikrotik-minder/commit/88e9833f84987f481f2d4bba36c056f8b4bd732a))

- **worker**: Align backup upload comment with 404 response
  ([`3f67f68`](https://github.com/MagmaMoose/mikrotik-minder/commit/3f67f687fe64b9cb1c924aebb1e985b73b5d2a7d))

- **worker**: Guard JSON.parse of command params in poll endpoint
  ([`f3bb389`](https://github.com/MagmaMoose/mikrotik-minder/commit/f3bb389f98e6515bfc193e49f1aa8ad4870a7814))

- **worker**: Null-check artifact before returning the download body
  ([`fef2059`](https://github.com/MagmaMoose/mikrotik-minder/commit/fef2059d5707157b8a3174de7549d2daa45204b5))

- **worker**: Reject arrays in command result validation
  ([`79f93c1`](https://github.com/MagmaMoose/mikrotik-minder/commit/79f93c19dec200f6686d1c85a534226c4734ba7d))

- **worker**: Restore SLACK_INFO_CHANNEL dropped in the #13 merge
  ([`2b11914`](https://github.com/MagmaMoose/mikrotik-minder/commit/2b1191427819df9fb45f5ad6d8a8dd9a25aaccef))

- **worker**: Return 202 for pending/claimed commands on artifact endpoint
  ([`8a26256`](https://github.com/MagmaMoose/mikrotik-minder/commit/8a262565f0fa4002e6e76894e47a911564151c54))

### Chores

- **chart**: Mikrotik-minder-agent 0.1.3 (appVersion 0.0.2)
  ([`d5077a5`](https://github.com/MagmaMoose/mikrotik-minder/commit/d5077a5e6111525f4a386d58ea029a2dcd37ec0e))

### Features

- Stream encrypted backups to R2 + Pro UI download endpoints
  ([`401417b`](https://github.com/MagmaMoose/mikrotik-minder/commit/401417bb5d8afa624908637a0efdba5d50331041))

- **agent**: Poll for operator-triggered commands and execute them
  ([`1d73490`](https://github.com/MagmaMoose/mikrotik-minder/commit/1d73490585ed7e5afb1fe1b39a4e0bbf93488a85))

- **worker**: Command-dispatch endpoints + commands table
  ([`74f18b1`](https://github.com/MagmaMoose/mikrotik-minder/commit/74f18b1aa7aec715d9c8de99fbb7ba971cda2821))

### Performance Improvements

- **ingest**: Eliminate N+1 query in GET /commands by joining device name
  ([`9b14323`](https://github.com/MagmaMoose/mikrotik-minder/commit/9b14323b33fc041e8490cdedefe1389a135072e7))

- **worker**: Add composite index for command claim query
  ([`3b7b130`](https://github.com/MagmaMoose/mikrotik-minder/commit/3b7b1309be5b1a1613bead74c6fafda9d3695df3))

### Refactoring

- **db**: Remove redundant commands_agent_idx index
  ([`4160ffa`](https://github.com/MagmaMoose/mikrotik-minder/commit/4160ffa5f50cc5eb1864a66521b75ac21fec4618))

- **minder**: Include HTTP status code in MinderError for robust 404 handling
  ([`ce58a3a`](https://github.com/MagmaMoose/mikrotik-minder/commit/ce58a3a21028ca97dc538154b56679f0e70d62b4))


## v1.4.0 (2026-05-23)

### Bug Fixes

- **admin**: Add anti-caching headers to artifact download endpoint
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **admin**: Derive requested_by from authenticated user instead of request body
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **admin**: Make artifact download atomic with UPDATE ... RETURNING
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **admin**: Populate requested_by from X-Auth-Email header
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **admin**: Return pre-update artifact in one-shot download endpoint
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **admin**: Validate X-Auth-Email header for commands endpoint
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **agent**: Align sensitive export docstring with CRLF normalization
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **agent**: Enforce artifact size limit in sensitive export command
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **agent**: Report command results for export/backup commands
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **agent**: Satisfy ruff (unused noqa + line length)
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **agent**: Wrap E501 in sensitive export size-limit message
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **agent**: Wrap long MinderError lines added by status_code refactor
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **daemon**: Accept CommandRef in _execute_command_via_daemon
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **daemon**: Update device timestamps after command execution
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **ingest**: Fix invalid SQL in command claim query
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **ingest**: Preserve artifact payload verbatim without trimming
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **worker**: Guard JSON.parse of command params in poll endpoint
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **worker**: Null-check artifact before returning the download body
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **worker**: Reject arrays in command result validation
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **worker**: Restore SLACK_INFO_CHANNEL dropped in the #13 merge
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **worker**: Return 202 for pending/claimed commands on artifact endpoint
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

### Chores

- **chart**: Mikrotik-minder-agent 0.1.3 (appVersion 0.0.2)
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

### Features

- **agent**: Poll for operator-triggered commands and execute them
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **worker**: Command-dispatch endpoints + commands table
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **worker**: Command-dispatch foundation (commands table + endpoints)
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

### Performance Improvements

- **ingest**: Eliminate N+1 query in GET /commands by joining device name
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **worker**: Add composite index for command claim query
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

### Refactoring

- **db**: Remove redundant commands_agent_idx index
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))

- **minder**: Include HTTP status code in MinderError for robust 404 handling
  ([#15](https://github.com/MagmaMoose/mikrotik-minder/pull/15),
  [`6b0c86d`](https://github.com/MagmaMoose/mikrotik-minder/commit/6b0c86d60a87fac92c827b78893f0e58e1b28f48))


## v1.3.0 (2026-05-22)

### Bug Fixes

- **worker**: Align Slack env doc with severity-based routing
  ([`b504eef`](https://github.com/MagmaMoose/mikrotik-minder/commit/b504eef14c3225c8d33ebb160623c560a0dda154))

### Documentation

- **agent-protocol**: Clarify alert_deliveries scope for Slack bot
  ([`d7b0367`](https://github.com/MagmaMoose/mikrotik-minder/commit/d7b0367d232dd29cbf78be81b2a08abf7f1bc6ec))

- **agent-protocol**: Fix Slack bot env var table to match implementation
  ([`33c4e3f`](https://github.com/MagmaMoose/mikrotik-minder/commit/33c4e3f5dde440324cfdd5f0ba4edea698ff2c99))

### Features

- **worker**: Route Slack alerts to 3 channels by kind + announce wins
  ([`e81a81b`](https://github.com/MagmaMoose/mikrotik-minder/commit/e81a81b953392934356633e726a746e7b55ab100))

- **worker**: Slack bot-token alert delivery
  ([`08d06c3`](https://github.com/MagmaMoose/mikrotik-minder/commit/08d06c3e254a29ea1de18e04fbc0733f88093155))


## v1.2.1 (2026-05-22)

### Bug Fixes

- **chart**: Keep the git deploy key's trailing newline
  ([`073f16e`](https://github.com/MagmaMoose/mikrotik-minder/commit/073f16ef11e2ee3b84418501596f582976734f86))


## v1.2.0 (2026-05-21)

### Bug Fixes

- **agent**: Default serviceAccountName to 'default' when create is false
  ([`dc74c81`](https://github.com/MagmaMoose/mikrotik-minder/commit/dc74c81b3cc5ac77b1a90d8569188b487c6ff4f2))

### Features

- Bump agent to 0.0.1 + restore chart's image/secret helpers
  ([`8d72c7d`](https://github.com/MagmaMoose/mikrotik-minder/commit/8d72c7d20834d1ed267b33aae3e9c29a88baccb4))


## v1.1.1 (2026-05-21)

### Bug Fixes

- Complete env.prod wrangler config + opt deploy into prod environment
  ([`118bfb9`](https://github.com/MagmaMoose/mikrotik-minder/commit/118bfb94703437c25dd3134ea84f93b7976a1ddf))


## v1.1.0 (2026-05-21)

### Bug Fixes

- Address review feedback on secrets, prod env isolation, wrangler pin
  ([`ca22381`](https://github.com/MagmaMoose/mikrotik-minder/commit/ca22381d4756742e1d052e071606e592cde38a20))


## v1.0.0 (2026-05-21)

### Bug Fixes

- Address PR #3 CodeQL findings and Copilot review comments
  ([`5a1cf24`](https://github.com/MagmaMoose/mikrotik-minder/commit/5a1cf2470cb6de057bf7e79b18282e2864e71834))

### Features

- MVP scaffold — worker, agent, Helm chart, real-router validation
  ([`945f615`](https://github.com/MagmaMoose/mikrotik-minder/commit/945f6157ef0b7c9ae343f48b00366de4a330bac6))


## v0.0.1 (2026-05-19)

- Initial Release
