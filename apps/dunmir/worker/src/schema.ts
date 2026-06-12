// Lightweight runtime validation. Kept dependency-free to stay small on Workers.
//
// Canonical contract: the enums and request/response shapes below mirror
// @platform/schemas (packages/schemas/src/dunmir.ts + the Pydantic side in
// packages/schemas/python/platform_schemas/dunmir.py). Change the contract
// THERE first, then keep this file in lockstep.

export type ValidationResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: string };

export function asString(v: unknown, field: string, opts: { max?: number; pattern?: RegExp } = {}): ValidationResult<string> {
  if (typeof v !== "string") return { ok: false, error: `${field} must be a string` };
  const trimmed = v.trim();
  if (trimmed.length === 0) return { ok: false, error: `${field} is required` };
  if (opts.max && trimmed.length > opts.max) return { ok: false, error: `${field} exceeds ${opts.max} chars` };
  if (opts.pattern && !opts.pattern.test(trimmed)) return { ok: false, error: `${field} format invalid` };
  return { ok: true, value: trimmed };
}

export function asOptionalString(v: unknown, field: string, opts: { max?: number } = {}): ValidationResult<string | undefined> {
  if (v === undefined || v === null || v === "") return { ok: true, value: undefined };
  return asString(v, field, opts);
}

export function asInt(v: unknown, field: string, opts: { min?: number; max?: number } = {}): ValidationResult<number> {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n) || !Number.isInteger(n)) return { ok: false, error: `${field} must be an integer` };
  if (opts.min !== undefined && n < opts.min) return { ok: false, error: `${field} must be >= ${opts.min}` };
  if (opts.max !== undefined && n > opts.max) return { ok: false, error: `${field} must be <= ${opts.max}` };
  return { ok: true, value: n };
}

export function asOptionalInt(v: unknown, field: string, opts: { min?: number; max?: number } = {}): ValidationResult<number | undefined> {
  if (v === undefined || v === null) return { ok: true, value: undefined };
  return asInt(v, field, opts);
}

export function asEnum<T extends string>(v: unknown, field: string, values: readonly T[]): ValidationResult<T> {
  if (typeof v !== "string" || !values.includes(v as T)) {
    return { ok: false, error: `${field} must be one of: ${values.join(", ")}` };
  }
  return { ok: true, value: v as T };
}

export function asStringArray(v: unknown, field: string): ValidationResult<string[] | undefined> {
  if (v === undefined || v === null) return { ok: true, value: undefined };
  if (!Array.isArray(v)) return { ok: false, error: `${field} must be an array` };
  for (const item of v) {
    if (typeof item !== "string") return { ok: false, error: `${field} must be an array of strings` };
  }
  return { ok: true, value: v as string[] };
}

export function asOptionalEnum<T extends string>(
  v: unknown,
  field: string,
  values: readonly T[],
): ValidationResult<T | undefined> {
  if (v === undefined || v === null || v === "") return { ok: true, value: undefined };
  return asEnum(v, field, values);
}

export function asOptionalBool(v: unknown, field: string): ValidationResult<boolean | undefined> {
  if (v === undefined || v === null) return { ok: true, value: undefined };
  if (typeof v !== "boolean") return { ok: false, error: `${field} must be a boolean` };
  return { ok: true, value: v };
}

// Device connection transports (control-plane-managed config).
export const TRANSPORTS = ["api", "ssh"] as const;
export type Transport = (typeof TRANSPORTS)[number];

export const JOB_KINDS = [
  "backup",
  "export",
  "drift",
  "update_check",
  "update_apply",
  "firmware_align",
  "health_check",
  "restore_validate",
  "inventory_sync",
] as const;

export const JOB_STATUSES = ["success", "warning", "failed", "skipped"] as const;

export const DEVICE_STATUSES = ["unknown", "ok", "degraded", "down"] as const;

export const ROUTE_KINDS = ["webhook", "slack", "discord"] as const;

export const SEVERITIES = ["info", "warning", "critical"] as const;

export const ALERT_KINDS = [
  "heartbeat_missed",
  "heartbeat_recovered",
  "job_failed",
  "drift_detected",
  "update_available",
  "update_failed",
  "backup_succeeded",
  "update_applied",
  "restore_due",
  "manual",
] as const;

export type JobKind = (typeof JOB_KINDS)[number];
export type JobStatus = (typeof JOB_STATUSES)[number];
export type DeviceStatus = (typeof DEVICE_STATUSES)[number];
export type RouteKind = (typeof ROUTE_KINDS)[number];
export type Severity = (typeof SEVERITIES)[number];
export type AlertKind = (typeof ALERT_KINDS)[number];

// Command dispatch — the operator-triggered actions the agent can be asked to
// run. `sensitive_export` is an /export WITHOUT hide-sensitive (passwords/keys).
export const COMMAND_KINDS = ["backup", "export", "update_apply", "sensitive_export"] as const;
export const COMMAND_STATUSES = [
  "pending",
  "claimed",
  "succeeded",
  "failed",
  "expired",
] as const;
export type CommandKind = (typeof COMMAND_KINDS)[number];
export type CommandStatus = (typeof COMMAND_STATUSES)[number];

export function severityRank(s: Severity): number {
  return s === "info" ? 0 : s === "warning" ? 1 : 2;
}

export function meetsSeverity(s: Severity, min: Severity): boolean {
  return severityRank(s) >= severityRank(min);
}
