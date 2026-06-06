"""Execute operator-triggered commands from the control plane.

The agent's interval-driven daemon (``daemon.py``) does heartbeats, exports,
backups, and update_checks on its own schedule. *This* module handles the
on-demand work the Pro UI enqueues: manual backup/export, update apply, and the
one-shot show-sensitive export download.

Every command produces (a) a ``commands.<id>`` result the Pro UI polls and (b)
where applicable, a parallel ``jobs`` row so the run shows up in the timeline
alongside the interval-driven ones.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .apply import (
    ApplyAborted,
    ApplyError,
    ApplyTimedOut,
    apply_summary,
    apply_update,
)
from .backup import BackupError, BackupRunner, backup_summary
from .config import AgentConfig, DeviceConfig
from .export import ExportError, ExportRunner
from .minder import CommandRef, JobReport, MinderClient, MinderError
from .transports import TransportError
from .transports.ssh import SSHTransport

log = logging.getLogger(__name__)

# Maximum artifact size accepted by the worker (must match worker/src/routes/ingest.ts)
_MAX_ARTIFACT_CHARS = 5_000_000


def execute_command(
    cmd: CommandRef,
    config: AgentConfig,
    *,
    minder: MinderClient,
    exporter: ExportRunner | None,
    backup_runner: BackupRunner | None,
) -> bool:
    """Dispatch one command end-to-end (run + report). Never raises.

    Returns True only when the underlying work succeeded; callers use this to
    gate side effects like advancing per-device interval timestamps so a failed
    operator-triggered run doesn't suppress the next scheduled one.
    """
    device = _device_by_name(config, cmd.device)
    if device is None:
        _report(minder, cmd.id, "failed", result={"error": f"unknown device {cmd.device!r}"})
        return False

    log.info("command %s: %s on %s", cmd.id, cmd.kind, device.name)
    try:
        if cmd.kind == "backup":
            return _run_backup(cmd, device, minder, backup_runner)
        elif cmd.kind == "export":
            return _run_export(cmd, device, minder, exporter)
        elif cmd.kind == "update_apply":
            return _run_update_apply(cmd, device, config, minder)
        elif cmd.kind == "sensitive_export":
            return _run_sensitive_export(cmd, device, config, minder)
        else:
            _report(
                minder,
                cmd.id,
                "failed",
                result={"error": f"unknown command kind {cmd.kind!r}"},
            )
            return False
    except Exception as exc:  # never let one bad command kill the whole poller
        log.exception("command %s dispatcher error", cmd.id)
        _report(minder, cmd.id, "failed", result={"error": f"dispatcher error: {exc}"})
        return False


# --- per-kind executors ----------------------------------------------------


def _run_backup(
    cmd: CommandRef,
    device: DeviceConfig,
    minder: MinderClient,
    runner: BackupRunner | None,
) -> bool:
    if runner is None:
        _report(minder, cmd.id, "failed", result={"error": "backup pipeline not configured"})
        return False
    started = int(time.time())
    try:
        res = runner.run(device, uploader=minder)
    except BackupError as exc:
        _report(minder, cmd.id, "failed", result={"error": str(exc)})
        _send_failure_job(minder, device, "backup", started, str(exc))
        return False

    details: dict[str, Any] = {
        "file_name": res.file_name,
        "file_path": res.file_path,
        "size_bytes": res.size_bytes,
        "sha256": res.sha256,
        "retained": res.retained,
        "pruned": res.pruned,
        "uploaded_id": res.uploaded_id,
        "upload_skipped": res.upload_skipped,
        "upload_error": res.upload_error,
    }
    summary = backup_summary(res)
    _send_job(
        minder, device, "backup", "success",
        res.started_at, res.finished_at, summary, details,
    )
    _report(minder, cmd.id, "succeeded", result={"summary": summary, **details})
    return True


def _run_export(
    cmd: CommandRef,
    device: DeviceConfig,
    minder: MinderClient,
    runner: ExportRunner | None,
) -> bool:
    if runner is None:
        _report(minder, cmd.id, "failed", result={"error": "export pipeline not configured"})
        return False
    started = int(time.time())
    try:
        res = runner.run(device)
    except ExportError as exc:
        _report(minder, cmd.id, "failed", result={"error": str(exc)})
        _send_failure_job(minder, device, "export", started, str(exc))
        return False

    push_failed = res.push_error is not None
    if push_failed:
        job_kind = "drift" if res.changed else "export"
        job_status = "failed"
    elif res.changed:
        job_kind, job_status = "drift", "warning"
    else:
        job_kind, job_status = "export", "success"

    details: dict[str, Any] = {
        "bytes_captured": res.bytes_captured,
        "changed": res.changed,
        "commit_sha": res.commit_sha,
        "lines_added": res.lines_added,
        "lines_removed": res.lines_removed,
        "relative_path": res.relative_path,
        "pushed": res.pushed,
        "push_skipped": res.push_skipped,
        "push_error": res.push_error,
    }
    summary = (
        f"export · drift · +{res.lines_added}/-{res.lines_removed} · {res.bytes_captured} bytes"
        if res.changed
        else f"export · no change · {res.bytes_captured} bytes"
    )
    _send_job(
        minder, device, job_kind, job_status, res.started_at, res.finished_at, summary, details,
    )
    _report(
        minder,
        cmd.id,
        "failed" if push_failed else "succeeded",
        result={"summary": summary, **details},
    )
    return not push_failed


def _run_update_apply(
    cmd: CommandRef,
    device: DeviceConfig,
    config: AgentConfig,
    minder: MinderClient,
) -> bool:
    mode = str(cmd.params.get("mode") or "now").strip().lower()
    if mode == "download_only":
        return _run_update_download_only(cmd, device, config, minder)
    # default → mode "now": full install + reboot.
    started = int(time.time())
    try:
        res = apply_update(
            config,
            device,
            ticket=f"cmd:{cmd.id}",
            min_free_mib=_get_float(cmd.params, "min_free_mib", 100.0),
            max_backup_age_seconds=_get_int(cmd.params, "max_backup_age_seconds", 24 * 60 * 60),
            max_wait_seconds=_get_int(cmd.params, "max_wait_seconds", 600),
            require_backup=_get_bool(cmd.params, "require_backup", default=True),
        )
    except ApplyAborted as exc:
        _report(
            minder,
            cmd.id,
            "failed",
            result={"error": str(exc), "aborted_pre_install": True},
        )
        _send_failure_job(minder, device, "update_apply", started, f"aborted: {exc}")
        return False
    except (ApplyTimedOut, ApplyError) as exc:
        _report(minder, cmd.id, "failed", result={"error": str(exc)})
        _send_failure_job(minder, device, "update_apply", started, str(exc))
        return False

    summary = apply_summary(res)
    details: dict[str, Any] = {
        "ticket": res.ticket,
        "before_version": res.before.version,
        "after_version": res.after.version,
        "downtime_seconds": res.downtime_seconds,
        "before_free": res.before.free_hdd_space,
        "after_free": res.after.free_hdd_space,
    }
    _send_job(
        minder, device, "update_apply", "success",
        res.started_at, res.finished_at, summary, details,
    )
    _report(minder, cmd.id, "succeeded", result={"summary": summary, **details})
    return True


def _run_update_download_only(
    cmd: CommandRef,
    device: DeviceConfig,
    config: AgentConfig,
    minder: MinderClient,
) -> bool:
    """Download the available update package but don't install/reboot."""
    ssh = SSHTransport(device, config.defaults)
    try:
        out = ssh.capture(
            "/system package update download",
            timeout=config.defaults.connect_timeout_seconds + 120,
        )
    except TransportError as exc:
        _report(minder, cmd.id, "failed", result={"error": f"download failed: {exc}"})
        return False
    _report(
        minder,
        cmd.id,
        "succeeded",
        result={"mode": "download_only", "output": (out or "").strip()[:500]},
    )
    return True


def _run_sensitive_export(
    cmd: CommandRef,
    device: DeviceConfig,
    config: AgentConfig,
    minder: MinderClient,
) -> bool:
    """Capture ``/export show-sensitive`` and return the text as a one-shot artifact.

    Unlike the regular export pipeline, the body is NOT committed to git, NOT
    persisted on the agent, and NOT normalised beyond CRLF→LF conversion. It is
    delivered exactly once via the control plane's purge-on-read artifact endpoint.
    """
    ssh = SSHTransport(device, config.defaults)
    try:
        text = ssh.capture(
            "/export show-sensitive",
            timeout=config.defaults.export_timeout_seconds,
        )
    except TransportError as exc:
        _report(minder, cmd.id, "failed", result={"error": f"capture failed: {exc}"})
        return False
    text = text.replace("\r\n", "\n")
    if len(text) > _MAX_ARTIFACT_CHARS:
        _report(
            minder,
            cmd.id,
            "failed",
            result={
                "error": (
                    f"sensitive export too large "
                    f"({len(text)} chars, max {_MAX_ARTIFACT_CHARS})"
                ),
                "bytes": len(text),
            },
        )
        return False
    _report(minder, cmd.id, "succeeded", result={"bytes": len(text)}, artifact=text)
    return True


# --- helpers ---------------------------------------------------------------


def _device_by_name(config: AgentConfig, name: str | None) -> DeviceConfig | None:
    if not name:
        return None
    for d in config.devices:
        if d.name == name:
            return d
    return None


def _report(
    minder: MinderClient,
    cmd_id: str,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    artifact: str | None = None,
) -> None:
    try:
        minder.report_command_result(cmd_id, status, result=result, artifact=artifact)
    except MinderError as exc:
        log.error("command %s: result report failed: %s", cmd_id, exc)


def _send_job(
    minder: MinderClient,
    device: DeviceConfig,
    kind: str,
    status: str,
    started_at: int,
    finished_at: int,
    summary: str,
    details: dict[str, Any],
) -> None:
    """Mirror the daemon's job-emit shape so commands show up in the run history."""
    try:
        minder.send_job(
            JobReport(
                device=device.name,
                kind=kind,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                summary=summary,
                details=details,
            ),
        )
    except MinderError as exc:
        log.warning("device %s %s job send failed: %s", device.name, kind, exc)


def _send_failure_job(
    minder: MinderClient,
    device: DeviceConfig,
    kind: str,
    started: int,
    error: str,
) -> None:
    finished = int(time.time())
    _send_job(
        minder, device, kind, "failed", started, finished,
        f"{kind} failed: {error[:200]}",
        {"error": error[:500]},
    )


def _get_int(d: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(d.get(key, default))
    except (TypeError, ValueError):
        return default


def _get_float(d: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(d.get(key, default))
    except (TypeError, ValueError):
        return default


def _get_bool(d: dict[str, Any], key: str, *, default: bool) -> bool:
    v = d.get(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return default
