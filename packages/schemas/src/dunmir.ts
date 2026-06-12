import { z } from "zod";

/**
 * Dün Mir (MikroTik Minder) worker↔agent ingest contract — zod side.
 *
 * Canonical shapes for the `/v1/ingest/*` protocol between the Cloudflare
 * worker (apps/dunmir/worker) and the on-prem agent (apps/dunmir/agent).
 * The Pydantic mirror lives in `python/platform_schemas/dunmir.py`; keep the
 * two in lockstep.
 *
 * Consumption note: the worker keeps its hand-rolled validators (deliberately
 * dependency-free to stay small on Workers) and the agent keeps stdlib
 * dataclasses (it's a published standalone CLI that intentionally avoids
 * Pydantic). Both are documented mirrors of THIS contract — change it here
 * first, then update both runtimes.
 */

// --- Enums (mirrors apps/dunmir/worker/src/schema.ts) -----------------------

export const Transport = z.enum(["api", "ssh"]);
export type Transport = z.infer<typeof Transport>;

export const JobKind = z.enum([
  "backup",
  "export",
  "drift",
  "update_check",
  "update_apply",
  "firmware_align",
  "health_check",
  "restore_validate",
  "inventory_sync",
]);
export type JobKind = z.infer<typeof JobKind>;

export const JobStatus = z.enum(["success", "warning", "failed", "skipped"]);
export type JobStatus = z.infer<typeof JobStatus>;

export const DeviceStatus = z.enum(["unknown", "ok", "degraded", "down"]);
export type DeviceStatus = z.infer<typeof DeviceStatus>;

export const RouteKind = z.enum(["webhook", "slack", "discord"]);
export type RouteKind = z.infer<typeof RouteKind>;

export const Severity = z.enum(["info", "warning", "critical"]);
export type Severity = z.infer<typeof Severity>;

export const AlertKind = z.enum([
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
]);
export type AlertKind = z.infer<typeof AlertKind>;

// `sensitive_export` is an /export WITHOUT hide-sensitive (passwords/keys).
export const CommandKind = z.enum(["backup", "export", "update_apply", "sensitive_export"]);
export type CommandKind = z.infer<typeof CommandKind>;

export const CommandStatus = z.enum(["pending", "claimed", "succeeded", "failed", "expired"]);
export type CommandStatus = z.infer<typeof CommandStatus>;

// --- POST /v1/ingest/heartbeat ----------------------------------------------

export const Heartbeat = z.object({
  device: z.string().min(1).max(100),
  status: DeviceStatus.default("ok"),
});
export type Heartbeat = z.infer<typeof Heartbeat>;

export const HeartbeatResponse = z.object({
  ok: z.literal(true),
  device_id: z.string(),
  created: z.boolean(),
});
export type HeartbeatResponse = z.infer<typeof HeartbeatResponse>;

// --- POST /v1/ingest/jobs ----------------------------------------------------

export const JobReport = z
  .object({
    kind: JobKind,
    status: JobStatus,
    started_at: z.number().int().min(0),
    finished_at: z.number().int().min(0),
    summary: z.string().max(500).nullish(),
    device: z.string().max(100).nullish(),
    details: z.record(z.unknown()).nullish(),
  })
  .refine((v) => v.finished_at >= v.started_at, {
    message: "finished_at must be >= started_at",
  });
export type JobReport = z.infer<typeof JobReport>;

// --- GET /v1/ingest/commands (claim) -----------------------------------------

export const CommandRef = z.object({
  id: z.string(),
  device: z.string().nullish(),
  kind: CommandKind,
  params: z.record(z.unknown()).default({}),
});
export type CommandRef = z.infer<typeof CommandRef>;

export const ClaimCommandsResponse = z.object({
  commands: z.array(CommandRef),
});
export type ClaimCommandsResponse = z.infer<typeof ClaimCommandsResponse>;

// --- POST /v1/ingest/commands/:id/result -------------------------------------

export const CommandResult = z.object({
  status: z.enum(["succeeded", "failed"]),
  result: z.record(z.unknown()).optional(),
  // One-shot sensitive-export body; only allowed for kind=sensitive_export.
  artifact: z.string().optional(),
});
export type CommandResult = z.infer<typeof CommandResult>;
