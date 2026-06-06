/**
 * A tiny D1Database shim over better-sqlite3, plus a two-tenant fixture.
 *
 * The point of the tenancy suite is to catch a *missing* tenant filter in any
 * real handler — so we run the actual Hono app and its real SQL against an
 * in-memory SQLite (schema = the real migrations), rather than re-asserting the
 * predicates in isolation. This shim implements just the slice of the D1 API the
 * worker uses: prepare().bind().first()/all()/run().
 */
import Database from "better-sqlite3";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const MIGRATIONS_DIR = join(HERE, "..", "migrations");

class ShimStatement {
  constructor(
    private readonly db: Database.Database,
    private readonly sql: string,
    private readonly params: unknown[] = [],
  ) {}

  bind(...params: unknown[]): ShimStatement {
    return new ShimStatement(this.db, this.sql, params);
  }

  /**
   * better-sqlite3 won't take D1's numbered `?N` placeholders positionally, so
   * rewrite each `?N` to an anonymous `?` and expand the bound values by
   * occurrence order (a reused `?1` binds its value once per occurrence).
   */
  private prepared(): { stmt: Database.Statement; values: unknown[] } {
    const values: unknown[] = [];
    const sql = this.sql.replace(/\?(\d+)/g, (_m, d: string) => {
      values.push(this.params[Number(d) - 1]);
      return "?";
    });
    return { stmt: this.db.prepare(sql), values };
  }

  async first<T = Record<string, unknown>>(column?: string): Promise<T | null> {
    const { stmt, values } = this.prepared();
    const row = stmt.get(...values) as Record<string, unknown> | undefined;
    if (row === undefined) return null;
    return column ? ((row[column] ?? null) as T) : (row as T);
  }

  async all<T = Record<string, unknown>>(): Promise<{ results: T[]; success: true; meta: object }> {
    const { stmt, values } = this.prepared();
    return { results: stmt.all(...values) as T[], success: true, meta: {} };
  }

  async run(): Promise<{ success: true; meta: object }> {
    const { stmt, values } = this.prepared();
    const info = stmt.run(...values);
    return { success: true, meta: { changes: info.changes, last_row_id: Number(info.lastInsertRowid) } };
  }
}

/** Wraps a better-sqlite3 handle in the subset of D1Database the worker calls. */
export class ShimD1 {
  constructor(private readonly db: Database.Database) {}
  prepare(sql: string): ShimStatement {
    return new ShimStatement(this.db, sql);
  }
}

/** Fresh in-memory DB with every migration applied, in order. */
export function migratedDb(): Database.Database {
  const db = new Database(":memory:");
  db.pragma("foreign_keys = ON");
  const files = readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(".sql"))
    .sort();
  for (const f of files) db.exec(readFileSync(join(MIGRATIONS_DIR, f), "utf8"));
  return db;
}

// Stable fixture ids — referenced by the assertions.
export const FX = {
  tenantA: "tnt_a",
  tenantB: "tnt_b",
  emailA: "alice@a.example",
  emailB: "bob@b.example",
  agentA: "agt_a",
  agentB: "agt_b",
  agentDefault: "agt_def",
  deviceA: "dev_a",
  deviceB: "dev_b",
  cmdA: "cmd_a",
  cmdB: "cmd_b",
  backupA: "bk_a",
  backupB: "bk_b",
  // Distinctive resource names so a leak shows up as one tenant's string
  // appearing in the other tenant's response body.
  nameAgentA: "agent-ALPHA",
  nameAgentB: "agent-BRAVO",
  nameDeviceA: "rtr-ALPHA",
  nameDeviceB: "rtr-BRAVO",
  nameRouteA: "route-ALPHA",
  nameRouteB: "route-BRAVO",
  fileA: "alpha-secret.backup",
  fileB: "bravo-secret.backup",
  artifactA: "ALPHA-EXPORT-BODY",
  artifactB: "BRAVO-EXPORT-BODY",
} as const;

/**
 * Seed two fully-populated tenants (A and B) plus one agent on the implicit
 * tnt_default (for the single-tenant inertness check). Every entity type that
 * the admin API exposes is represented for both tenants.
 */
export function seedTwoTenants(db: Database.Database): void {
  const t = 1_700_000_000;
  db.exec(`
    INSERT INTO tenants (id, name, created_at) VALUES
      ('${FX.tenantA}', 'Alpha', ${t}),
      ('${FX.tenantB}', 'Bravo', ${t});

    INSERT INTO tenant_members (email, tenant_id, created_at) VALUES
      ('${FX.emailA}', '${FX.tenantA}', ${t}),
      ('${FX.emailB}', '${FX.tenantB}', ${t});

    INSERT INTO agents (id, name, token_hash, created_at, tenant_id) VALUES
      ('${FX.agentA}', '${FX.nameAgentA}', 'hash_a', ${t}, '${FX.tenantA}'),
      ('${FX.agentB}', '${FX.nameAgentB}', 'hash_b', ${t}, '${FX.tenantB}'),
      ('${FX.agentDefault}', 'agent-DEFAULT', 'hash_def', ${t}, 'tnt_default');

    INSERT INTO devices (id, agent_id, name, last_status, created_at) VALUES
      ('${FX.deviceA}', '${FX.agentA}', '${FX.nameDeviceA}', 'ok', ${t}),
      ('${FX.deviceB}', '${FX.agentB}', '${FX.nameDeviceB}', 'ok', ${t});

    INSERT INTO jobs (id, agent_id, device_id, kind, status, started_at, finished_at, created_at) VALUES
      ('job_a', '${FX.agentA}', '${FX.deviceA}', 'export', 'ok', ${t}, ${t}, ${t}),
      ('job_b', '${FX.agentB}', '${FX.deviceB}', 'export', 'ok', ${t}, ${t}, ${t});

    INSERT INTO commands (id, device_id, agent_id, kind, status, created_at, artifact) VALUES
      ('${FX.cmdA}', '${FX.deviceA}', '${FX.agentA}', 'sensitive_export', 'succeeded', ${t}, '${FX.artifactA}'),
      ('${FX.cmdB}', '${FX.deviceB}', '${FX.agentB}', 'sensitive_export', 'succeeded', ${t}, '${FX.artifactB}');

    INSERT INTO alert_routes (id, name, kind, url, min_severity, enabled, created_at, tenant_id) VALUES
      ('ar_a', '${FX.nameRouteA}', 'webhook', 'https://alpha.example/hook', 'warning', 1, ${t}, '${FX.tenantA}'),
      ('ar_b', '${FX.nameRouteB}', 'webhook', 'https://bravo.example/hook', 'warning', 1, ${t}, '${FX.tenantB}');

    INSERT INTO backup_files (id, agent_id, device_id, file_name, r2_key, size_bytes, sha256, created_at) VALUES
      ('${FX.backupA}', '${FX.agentA}', '${FX.deviceA}', '${FX.fileA}', 'backups/${FX.deviceA}/${FX.fileA}', 10, 'sha_a', ${t}),
      ('${FX.backupB}', '${FX.agentB}', '${FX.deviceB}', '${FX.fileB}', 'backups/${FX.deviceB}/${FX.fileB}', 10, 'sha_b', ${t});
  `);
}
