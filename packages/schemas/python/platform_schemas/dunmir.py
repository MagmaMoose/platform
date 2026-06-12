"""Dün Mir (MikroTik Minder) worker↔agent ingest contract — Pydantic v2 side.

Mirror of the zod shapes in ``../../src/dunmir.ts``. Canonical shapes for the
``/v1/ingest/*`` protocol between the Cloudflare worker (apps/dunmir/worker)
and the on-prem agent (apps/dunmir/agent). Keep the two in lockstep.

The worker keeps hand-rolled validators (deliberately dependency-free on
Workers) and the agent keeps stdlib dataclasses (published standalone CLI that
intentionally avoids Pydantic) — both are documented mirrors of THIS contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Transport(str, Enum):
    api = "api"
    ssh = "ssh"


class JobKind(str, Enum):
    backup = "backup"
    export = "export"
    drift = "drift"
    update_check = "update_check"
    update_apply = "update_apply"
    firmware_align = "firmware_align"
    health_check = "health_check"
    restore_validate = "restore_validate"
    inventory_sync = "inventory_sync"


class JobStatus(str, Enum):
    success = "success"
    warning = "warning"
    failed = "failed"
    skipped = "skipped"


class DeviceStatus(str, Enum):
    unknown = "unknown"
    ok = "ok"
    degraded = "degraded"
    down = "down"


class RouteKind(str, Enum):
    webhook = "webhook"
    slack = "slack"
    discord = "discord"


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertKind(str, Enum):
    heartbeat_missed = "heartbeat_missed"
    heartbeat_recovered = "heartbeat_recovered"
    job_failed = "job_failed"
    drift_detected = "drift_detected"
    update_available = "update_available"
    update_failed = "update_failed"
    backup_succeeded = "backup_succeeded"
    update_applied = "update_applied"
    restore_due = "restore_due"
    manual = "manual"


class CommandKind(str, Enum):
    """`sensitive_export` is an /export WITHOUT hide-sensitive (passwords/keys)."""

    backup = "backup"
    export = "export"
    update_apply = "update_apply"
    sensitive_export = "sensitive_export"


class CommandStatus(str, Enum):
    pending = "pending"
    claimed = "claimed"
    succeeded = "succeeded"
    failed = "failed"
    expired = "expired"


# --- POST /v1/ingest/heartbeat ----------------------------------------------


class Heartbeat(BaseModel):
    device: str = Field(min_length=1, max_length=100)
    status: DeviceStatus = DeviceStatus.ok


class HeartbeatResponse(BaseModel):
    ok: Literal[True]
    device_id: str
    created: bool


# --- POST /v1/ingest/jobs ----------------------------------------------------


class JobReport(BaseModel):
    kind: JobKind
    status: JobStatus
    started_at: int = Field(ge=0)
    finished_at: int = Field(ge=0)
    summary: str | None = Field(default=None, max_length=500)
    device: str | None = Field(default=None, max_length=100)
    details: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _finished_not_before_started(self) -> "JobReport":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")
        return self


# --- GET /v1/ingest/commands (claim) ------------------------------------------


class CommandRef(BaseModel):
    id: str
    device: str | None = None
    kind: CommandKind
    params: dict[str, Any] = Field(default_factory=dict)


class ClaimCommandsResponse(BaseModel):
    commands: list[CommandRef] = Field(default_factory=list)


# --- POST /v1/ingest/commands/:id/result --------------------------------------


class CommandResult(BaseModel):
    status: Literal["succeeded", "failed"]
    result: dict[str, Any] | None = None
    # One-shot sensitive-export body; only allowed for kind=sensitive_export.
    artifact: str | None = None
