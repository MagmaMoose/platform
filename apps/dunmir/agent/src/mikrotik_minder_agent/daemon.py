"""Per-device tick loop.

Each device gets one background thread that probes on its own interval. Failures
flip the device to ``status=down`` until a probe succeeds again; the worker mirrors
that with its own dead-man alert if the agent itself stops checking in.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .backup import BackupError, BackupResult, BackupRunner, backup_summary
from .commands import execute_command
from .config import (
    AgentConfig,
    DeviceConfig,
    backup_interval,
    export_interval,
    heartbeat_interval,
    inventory_check_interval,
    ping_target,
    update_check_interval,
    with_managed_pipelines,
)
from .export import ExportError, ExportResult, ExportRunner
from .inventory import InventoryError, inventory_summary, run_inventory
from .minder import CommandRef, JobReport, MinderClient, MinderError
from .ping import PingError, run_ping
from .remoteconfig import build_devices, build_git_remote, devices_changed, git_remote_changed
from .transports import ProbeResult, TransportError, build_transports
from .updates import (
    UpdateCheckError,
    UpdateCheckResult,
    run_update_check,
    update_summary,
)

log = logging.getLogger(__name__)

# Spread each device's first heavy job (export / update_check / backup) across a
# short window after start-up. Per-device schedule state is in-memory only, so a
# pod restart would otherwise re-run everything for every device on the first
# tick — a 20-device fleet would hammer all routers (and queue 20 git commits)
# at once. Offset is deterministic per device index and capped so even large
# fleets stay bounded.
_STARTUP_STAGGER_STEP_SECONDS = 10.0
_STARTUP_STAGGER_MAX_SECONDS = 300.0


@dataclass
class DeviceState:
    last_status: str = "unknown"
    last_probe: float = 0.0
    last_export: float = 0.0
    last_update_check: float = 0.0
    last_backup: float = 0.0
    last_inventory: float = 0.0
    consecutive_failures: int = 0
    startup_offset: float = 0.0  # seconds to delay this device's first tick (anti-stampede)
    lock: threading.Lock = field(default_factory=threading.Lock)


class Daemon:
    """Runs one thread per device. Call ``run()`` to block, or ``run_once()`` for cron-style."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        dry_run: bool = False,
        unseal: Callable[[str], str] | None = None,
    ) -> None:
        # Control-plane agents get PVC-backed export + backup pipelines so a
        # freshly-added device is captured and backed up with no extra config.
        config = with_managed_pipelines(config)
        self._config = config
        self._dry_run = dry_run
        self._unseal = unseal  # decrypts sealed (vault) credentials on config refresh
        self._stop = threading.Event()
        # Stagger first ticks so a (re)start doesn't stampede the whole fleet.
        self._state: dict[str, DeviceState] = {
            d.name: DeviceState(
                startup_offset=min(
                    index * _STARTUP_STAGGER_STEP_SECONDS, _STARTUP_STAGGER_MAX_SECONDS,
                ),
            )
            for index, d in enumerate(config.devices)
        }
        self._exporter: ExportRunner | None = None
        if config.git is not None:
            try:
                self._exporter = ExportRunner(config)
            except ExportError as exc:
                log.error("export pipeline disabled: %s", exc)
        self._backup_runner: BackupRunner | None = None
        if config.backup is not None:
            try:
                self._backup_runner = BackupRunner(config)
            except BackupError as exc:
                log.error("backup pipeline disabled: %s", exc)

    # --- Public entry points ---

    def run(self) -> None:
        self._install_signal_handlers()
        with MinderClient(self._config.server) as minder:
            threads = [
                threading.Thread(
                    target=self._device_loop,
                    args=(d, minder),
                    name=f"dev:{d.name}",
                    daemon=True,
                )
                for d in self._config.devices
            ]
            # One extra thread polls the control plane for operator-triggered
            # commands (manual backup/export, update_apply, sensitive_export).
            threads.append(
                threading.Thread(
                    target=self._command_loop,
                    args=(minder,),
                    name="commands",
                    daemon=True,
                ),
            )
            # Remote-config agents re-fetch their device list periodically and
            # restart to apply changes (see _config_refresh_loop).
            if self._config.config_source == "remote":
                threads.append(
                    threading.Thread(
                        target=self._config_refresh_loop,
                        args=(minder,),
                        name="config-refresh",
                        daemon=True,
                    ),
                )
            for t in threads:
                t.start()
            log.info(
                "agent running with %d device(s) + command poller; ctrl-c to stop",
                len(self._config.devices),
            )
            try:
                while not self._stop.is_set():
                    self._stop.wait(timeout=1.0)
            finally:
                self._stop.set()
                log.info("shutting down")
                for t in threads:
                    t.join(timeout=5.0)

    def _config_refresh_loop(self, minder: MinderClient) -> None:
        """Remote mode: re-fetch the device config every
        ``config_refresh_interval_seconds`` and, when it changes, trigger a
        graceful shutdown so the process restarts and re-applies via the startup
        path (an internal exit → the orchestrator restarts the pod; a SIGTERM
        from the orchestrator stays down). A failed fetch is ignored — we keep
        running on the last-known-good config rather than thrashing on a blip.
        """
        interval = self._config.defaults.config_refresh_interval_seconds
        if self._config.config_source != "remote" or interval <= 0:
            return
        while not self._stop.wait(timeout=interval):
            try:
                doc = minder.fetch_config()
            except MinderError as exc:
                log.warning("config refresh failed (%s); keeping current config", exc)
                continue
            fetched = build_devices(doc, unseal=self._unseal)
            devices_diff = devices_changed(self._config.devices, fetched)
            # Only a git-remote change matters when this agent actually HAS an
            # export pipeline to push from. If managed pipelines are disabled
            # (config.git is None — e.g. an unwritable state dir), ignore remote
            # diffs so we don't restart-loop trying to apply something we can't.
            remote_diff = False
            if self._config.git is not None:
                fetched_remote = build_git_remote(doc, unseal=self._unseal)
                remote_diff = git_remote_changed(self._config.git.remote, fetched_remote)
            if devices_diff or remote_diff:
                log.info(
                    "control-plane config changed (devices %s, git remote %s) — restarting",
                    "changed" if devices_diff else "same",
                    "changed" if remote_diff else "same",
                )
                self._stop.set()
                return

    def run_once(self) -> int:
        """One pass over devices + one command-poll. Returns the count of failed probes."""
        failures = 0
        with MinderClient(self._config.server) as minder:
            for d in self._config.devices:
                if not self._tick(d, minder):
                    failures += 1
            try:
                commands = minder.get_commands()
            except MinderError as exc:
                log.warning("command poll failed: %s", exc)
                commands = []
            for cmd in commands:
                execute_command(
                    cmd,
                    self._config,
                    minder=minder,
                    exporter=self._exporter,
                    backup_runner=self._backup_runner,
                )
        return failures

    # --- Per-device loop ---

    def _device_loop(self, device: DeviceConfig, minder: MinderClient) -> None:
        interval = heartbeat_interval(device, self._config.defaults)
        offset = self._state[device.name].startup_offset
        log.info("device %s: every %ds (first tick +%.0fs)", device.name, interval, offset)
        # Hold off the first tick by this device's stagger offset so heartbeats and
        # heavy jobs spread out after start-up instead of all firing at once.
        if offset and self._stop.wait(timeout=offset):
            return
        while not self._stop.is_set():
            try:
                self._tick(device, minder)
            except Exception:
                # A single tick must never kill this device's thread — that would
                # silently take the router dark with no further probes or alerts.
                log.exception("device %s: unexpected error in tick (continuing)", device.name)
            if self._stop.wait(timeout=interval):
                break

    def _command_loop(self, minder: MinderClient) -> None:
        """Poll the control plane for queued commands and dispatch them.

        One thread for the whole agent — commands are agent-wide, not per-device.
        A failed poll is logged and the loop continues at the next interval; a
        stuck command stays visible to operators until the next successful poll.
        """
        interval = 30  # seconds; click-to-execute latency upper bound
        log.info("command poller: every %ds", interval)
        while not self._stop.is_set():
            try:
                commands = minder.get_commands()
            except MinderError as exc:
                log.warning("command poll failed: %s", exc)
                commands = []
            for cmd in commands:
                if self._stop.is_set():
                    break
                # Route through daemon helpers so device timestamps are updated
                # and duplicate interval-driven work is avoided.
                self._execute_command_via_daemon(cmd, minder)
            if self._stop.wait(timeout=interval):
                break

    def _execute_command_via_daemon(self, cmd: CommandRef, minder: MinderClient) -> None:
        """Execute a command and update the relevant device state timestamps."""
        # Determine the device name from the command payload.
        device_name = cmd.device
        if not device_name:
            log.warning("command missing device, skipping timestamp update")
            execute_command(
                cmd,
                self._config,
                minder=minder,
                exporter=self._exporter,
                backup_runner=self._backup_runner,
            )
            return

        # Find the device config.
        device = next((d for d in self._config.devices if d.name == device_name), None)
        if device is None:
            log.warning("command for unknown device %s, skipping timestamp update", device_name)
            execute_command(
                cmd,
                self._config,
                minder=minder,
                exporter=self._exporter,
                backup_runner=self._backup_runner,
            )
            return

        # Determine the command kind.
        command_kind = cmd.kind
        if command_kind in ("export", "sensitive_export"):
            success = execute_command(
                cmd,
                self._config,
                minder=minder,
                exporter=self._exporter,
                backup_runner=self._backup_runner,
            )
            if success:
                state = self._state[device.name]
                with state.lock:
                    state.last_export = time.time()
        elif command_kind == "backup":
            success = execute_command(
                cmd,
                self._config,
                minder=minder,
                exporter=self._exporter,
                backup_runner=self._backup_runner,
            )
            if success:
                state = self._state[device.name]
                with state.lock:
                    state.last_backup = time.time()
        else:
            # For other commands (e.g., update_apply), just execute directly.
            execute_command(
                cmd,
                self._config,
                minder=minder,
                exporter=self._exporter,
                backup_runner=self._backup_runner,
            )

    def _tick(self, device: DeviceConfig, minder: MinderClient) -> bool:
        started = int(time.time())
        result: ProbeResult | None = None
        error: str | None = None
        transport_kind = "none"
        # Per-transport probe outcome (api/ssh) so the UI can show a status light
        # for each, not just the winner. kind -> (ProbeResult | None, reason | None).
        probes: dict[str, tuple[ProbeResult | None, str | None]] = {}

        if self._dry_run:
            transport_kind = "dry"
            result = ProbeResult(kind="dry", identity=device.name, version="dry-run", latency_ms=0)
        else:
            try:
                transports = build_transports(device, self._config.defaults)
            except TransportError as exc:
                error = str(exc)
                transports = []
            # Probe every configured transport (not just until the first success) so
            # both API and SSH report a reachable/failed status each tick. The first
            # success — primary first — still wins for the device's identity/version.
            for t in transports:
                try:
                    probe = t.probe()
                    probes[t.kind] = (probe, None)
                    if result is None:
                        result = probe
                        transport_kind = t.kind
                        error = None
                except TransportError as exc:
                    probes[t.kind] = (None, str(exc))
                    if result is None:
                        transport_kind = t.kind  # last tried, until something succeeds
                        error = str(exc)
                    # Per-transport failures are expected steady state (e.g. SSH
                    # intentionally blocked while API works) — debug, not warning,
                    # so they don't flood the log every tick. A genuinely-down
                    # device gets one WARNING below.
                    log.debug("device %s %s probe failed: %s", device.name, t.kind, exc)

        finished = int(time.time())
        ok = result is not None
        status_label = "ok" if ok else "down"
        # Log the WINNING transport on success too — otherwise only failures show,
        # which makes a healthy API probe invisible next to a failing SSH inventory.
        if ok and result is not None and not self._dry_run:
            log.info(
                "device %s reachable via %s (RouterOS %s%s, %dms)",
                device.name,
                transport_kind,
                result.version or "?",
                f", identity {result.identity}" if result.identity else "",
                result.latency_ms,
            )
        elif not ok and not self._dry_run:
            # One warning when the device is genuinely down (every transport failed),
            # rather than one per failed transport above.
            log.warning("device %s unreachable: %s", device.name, error or "all transports failed")

        # Optional packet-loss probe (router → ping_target), folded into the same
        # health_check report. Off unless a ping_target is configured, so we never
        # generate surprise egress from the fleet.
        packet_loss_pct: float | None = None
        avg_rtt_ms: float | None = None
        target = ping_target(device, self._config.defaults)
        if ok and not self._dry_run and target:
            try:
                ping = run_ping(
                    device, self._config.defaults, target, self._config.defaults.ping_count,
                )
                packet_loss_pct = ping.packet_loss_pct
                avg_rtt_ms = ping.avg_rtt_ms
            except (PingError, TransportError) as exc:
                log.warning("device %s ping probe failed: %s", device.name, exc)

        probe_ok = self._report(
            device,
            minder,
            ok=ok,
            status_label=status_label,
            transport_kind=transport_kind,
            result=result,
            error=error,
            started=started,
            finished=finished,
            packet_loss_pct=packet_loss_pct,
            avg_rtt_ms=avg_rtt_ms,
            probes=probes,
        )

        # Only attempt heavier jobs when the device responded — no point hammering a down router.
        if ok and not self._dry_run:
            if self._export_due(device, finished):
                self._run_export(device, minder)
            if self._update_check_due(device, finished):
                self._run_update_check(device, minder)
            if self._inventory_due(device, finished):
                self._run_inventory(device, minder)
            if self._backup_due(device, finished):
                self._run_backup(device, minder)

        return probe_ok

    def _report(
        self,
        device: DeviceConfig,
        minder: MinderClient,
        *,
        ok: bool,
        status_label: str,
        transport_kind: str,
        result: ProbeResult | None,
        error: str | None,
        started: int,
        finished: int,
        packet_loss_pct: float | None = None,
        avg_rtt_ms: float | None = None,
        probes: dict[str, tuple[ProbeResult | None, str | None]] | None = None,
    ) -> bool:
        state = self._state[device.name]
        with state.lock:
            previous = state.last_status
            state.last_probe = finished
            state.last_status = status_label
            state.consecutive_failures = 0 if ok else state.consecutive_failures + 1
            failures = state.consecutive_failures

        try:
            minder.send_heartbeat(device.name, status=status_label)
        except MinderError as exc:
            log.error("device %s heartbeat send failed: %s", device.name, exc)
            return False

        summary = self._summary(ok, transport_kind, result, error)
        details: dict[str, object] = {
            "transport": transport_kind,
            "consecutive_failures": failures,
        }
        if result:
            details["identity"] = result.identity
            details["version"] = result.version
            details["latency_ms"] = result.latency_ms
            if result.board:
                details["board"] = result.board
            if result.routerboard is not None:
                rb = result.routerboard
                details["routerboard"] = {
                    "model": rb.model,
                    "serial": rb.serial,
                    "current_firmware": rb.current_firmware,
                    "upgrade_firmware": rb.upgrade_firmware,
                    "mismatch": rb.mismatch,
                }
        if probes:
            # Per-transport reachability so the UI shows an API and an SSH light.
            details["transports"] = {
                kind: {
                    "ok": probe is not None,
                    "latency_ms": probe.latency_ms if probe is not None else None,
                    "reason": reason,
                }
                for kind, (probe, reason) in probes.items()
            }
        if packet_loss_pct is not None:
            details["packet_loss_pct"] = packet_loss_pct
        if avg_rtt_ms is not None:
            details["avg_rtt_ms"] = avg_rtt_ms
        if error:
            details["error"] = error[:300]

        try:
            minder.send_job(
                JobReport(
                    device=device.name,
                    kind="health_check",
                    status="success" if ok else "failed",
                    started_at=started,
                    finished_at=finished,
                    summary=summary,
                    details=details,
                ),
            )
        except MinderError as exc:
            # The heartbeat already conveyed the device's status; a failed
            # secondary job POST must not flip a healthy device to "failed".
            log.error("device %s job send failed: %s", device.name, exc)
            return ok

        if previous != status_label:
            log.info("device %s status %s -> %s", device.name, previous, status_label)
        return ok

    # --- Export ---

    def _export_due(self, device: DeviceConfig, now: float) -> bool:
        if self._exporter is None:
            return False
        interval = export_interval(device, self._config.defaults)
        if not interval:
            return False
        state = self._state[device.name]
        with state.lock:
            last = state.last_export
        return last == 0.0 or now - last >= interval

    def _run_export(self, device: DeviceConfig, minder: MinderClient) -> None:
        assert self._exporter is not None
        started = int(time.time())
        try:
            result: ExportResult = self._exporter.run(device)
        except ExportError as exc:
            log.warning("device %s export failed: %s", device.name, exc)
            self._report_export_failure(device, minder, started, str(exc))
            return

        state = self._state[device.name]
        with state.lock:
            state.last_export = float(result.finished_at)

        # A push failure means the offsite mirror is behind; treat that as a job failure
        # regardless of whether there was config drift. The local commit still landed
        # so operators can investigate from disk; the worker fires job_failed.
        push_failed = result.push_error is not None
        if push_failed:
            kind = "drift" if result.changed else "export"
            status = "failed"
        elif result.changed:
            kind, status = "drift", "warning"
        else:
            kind, status = "export", "success"
        summary = self._export_summary(result)
        details: dict[str, object] = {
            "bytes_captured": result.bytes_captured,
            "changed": result.changed,
            "commit_sha": result.commit_sha,
            "lines_added": result.lines_added,
            "lines_removed": result.lines_removed,
            "relative_path": result.relative_path,
            "pushed": result.pushed,
            "push_skipped": result.push_skipped,
            "push_error": result.push_error,
        }
        try:
            minder.send_job(
                JobReport(
                    device=device.name,
                    kind=kind,
                    status=status,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    summary=summary,
                    details=details,
                ),
            )
        except MinderError as exc:
            log.error("device %s export send failed: %s", device.name, exc)

    def _report_export_failure(
        self,
        device: DeviceConfig,
        minder: MinderClient,
        started: int,
        error: str,
    ) -> None:
        finished = int(time.time())
        try:
            minder.send_job(
                JobReport(
                    device=device.name,
                    kind="export",
                    status="failed",
                    started_at=started,
                    finished_at=finished,
                    summary=f"export failed: {error[:200]}",
                    details={"error": error[:500]},
                ),
            )
        except MinderError as exc:
            log.error("device %s export failure send failed: %s", device.name, exc)

    # --- Update check ---

    def _update_check_due(self, device: DeviceConfig, now: float) -> bool:
        interval = update_check_interval(device, self._config.defaults)
        if not interval:
            return False
        state = self._state[device.name]
        with state.lock:
            last = state.last_update_check
        return last == 0.0 or now - last >= interval

    def _run_update_check(self, device: DeviceConfig, minder: MinderClient) -> None:
        started = int(time.time())
        try:
            result: UpdateCheckResult = run_update_check(device, self._config.defaults)
        except UpdateCheckError as exc:
            log.warning("device %s update_check failed: %s", device.name, exc)
            self._send_failure_job(device, minder, "update_check", started, str(exc))
            return

        state = self._state[device.name]
        with state.lock:
            state.last_update_check = float(result.finished_at)

        # update_check job: success when up-to-date, warning when an update is available.
        upd = result.update
        status = "warning" if upd.available else "success"
        details: dict[str, object] = {
            "channel": upd.channel,
            "installed_version": upd.installed_version,
            "latest_version": upd.latest_version,
            "status": upd.status,
            "available": upd.available,
        }
        try:
            minder.send_job(
                JobReport(
                    device=device.name,
                    kind="update_check",
                    status=status,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    summary=update_summary(result),
                    details=details,
                ),
            )
        except MinderError as exc:
            log.error("device %s update_check send failed: %s", device.name, exc)

        # firmware_align job: only post when this device has routerboard firmware to report on.
        fw = result.firmware
        if not fw.has_routerboard:
            return
        fw_status = "warning" if fw.mismatch else "success"
        fw_details: dict[str, object] = {
            "model": fw.model,
            "current_firmware": fw.current_firmware,
            "upgrade_firmware": fw.upgrade_firmware,
            "mismatch": fw.mismatch,
        }
        fw_summary = (
            f"firmware mismatch {fw.current_firmware} → {fw.upgrade_firmware}"
            if fw.mismatch
            else f"firmware aligned at {fw.current_firmware}"
        )
        try:
            minder.send_job(
                JobReport(
                    device=device.name,
                    kind="firmware_align",
                    status=fw_status,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    summary=fw_summary,
                    details=fw_details,
                ),
            )
        except MinderError as exc:
            log.error("device %s firmware_align send failed: %s", device.name, exc)

    # --- Inventory ---

    def _inventory_due(self, device: DeviceConfig, now: float) -> bool:
        interval = inventory_check_interval(device, self._config.defaults)
        if not interval:
            return False
        state = self._state[device.name]
        with state.lock:
            last = state.last_inventory
        return last == 0.0 or now - last >= interval

    def _run_inventory(self, device: DeviceConfig, minder: MinderClient) -> None:
        try:
            result = run_inventory(device, self._config.defaults)
        except InventoryError as exc:
            # Best-effort metadata — and it's SSH-only, so an API-only device would
            # fail this every hour. Log and skip rather than firing a job_failed
            # alert; the health_check already covers genuine unreachability.
            log.warning("device %s inventory skipped: %s", device.name, exc)
            return

        state = self._state[device.name]
        with state.lock:
            state.last_inventory = float(result.finished_at)

        details: dict[str, object] = {
            "address": result.address,
            "identity": result.identity,
            "has_routerboard": result.has_routerboard,
            "is_chr": not result.has_routerboard,
            "model": result.model,
            "license_level": result.license.level,
            "license_software_id": result.license.software_id,
            "license_deadline": result.license.deadline,
            "cloud_dns_name": result.cloud.dns_name,
            "cloud_public_address": result.cloud.public_address,
            "cloud_status": result.cloud.status,
            "ddns_enabled": result.cloud.ddns_enabled,
        }
        try:
            minder.send_job(
                JobReport(
                    device=device.name,
                    kind="inventory_sync",
                    status="success",
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    summary=inventory_summary(result),
                    details=details,
                ),
            )
        except MinderError as exc:
            log.error("device %s inventory send failed: %s", device.name, exc)

    def _send_failure_job(
        self,
        device: DeviceConfig,
        minder: MinderClient,
        kind: str,
        started: int,
        error: str,
    ) -> None:
        finished = int(time.time())
        try:
            minder.send_job(
                JobReport(
                    device=device.name,
                    kind=kind,
                    status="failed",
                    started_at=started,
                    finished_at=finished,
                    summary=f"{kind} failed: {error[:200]}",
                    details={"error": error[:500]},
                ),
            )
        except MinderError as exc:
            log.error("device %s %s failure send failed: %s", device.name, kind, exc)

    # --- Backup ---

    def _backup_due(self, device: DeviceConfig, now: float) -> bool:
        if self._backup_runner is None:
            return False
        interval = backup_interval(device, self._config.defaults)
        if not interval:
            return False
        state = self._state[device.name]
        with state.lock:
            last = state.last_backup
        return last == 0.0 or now - last >= interval

    def _run_backup(self, device: DeviceConfig, minder: MinderClient) -> None:
        assert self._backup_runner is not None
        started = int(time.time())
        try:
            # Pass the MinderClient as uploader so the encrypted body lands in
            # R2 + the worker's catalog as part of the same run. Upload errors
            # are non-fatal and reported in BackupResult.upload_error.
            result: BackupResult = self._backup_runner.run(device, uploader=minder)
        except BackupError as exc:
            log.warning("device %s backup failed: %s", device.name, exc)
            self._send_failure_job(device, minder, "backup", started, str(exc))
            return

        state = self._state[device.name]
        with state.lock:
            state.last_backup = float(result.finished_at)

        details: dict[str, object] = {
            "file_name": result.file_name,
            "file_path": result.file_path,
            "size_bytes": result.size_bytes,
            "sha256": result.sha256,
            "retained": result.retained,
            "pruned": result.pruned,
            "uploaded_id": result.uploaded_id,
            "upload_skipped": result.upload_skipped,
            "upload_error": result.upload_error,
        }
        try:
            minder.send_job(
                JobReport(
                    device=device.name,
                    kind="backup",
                    status="success",
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    summary=backup_summary(result),
                    details=details,
                ),
            )
        except MinderError as exc:
            log.error("device %s backup send failed: %s", device.name, exc)

    @staticmethod
    def _export_summary(result: ExportResult) -> str:
        if not result.changed:
            base = f"export ok · no changes · {result.bytes_captured} bytes"
        else:
            sha = (result.commit_sha or "")[:7]
            base = (
                f"drift · +{result.lines_added}/-{result.lines_removed} lines · "
                f"commit {sha} · {result.bytes_captured} bytes"
            )
        if result.push_error:
            return f"{base} · push FAILED: {result.push_error[:120]}"
        if result.pushed:
            return f"{base} · pushed"
        return base

    @staticmethod
    def _summary(ok: bool, kind: str, result: ProbeResult | None, error: str | None) -> str:
        if ok and result:
            ident = result.identity or "?"
            ver = result.version or "?"
            return f"{kind} ok · {ident} · ROS {ver} · {result.latency_ms}ms"
        return f"{kind} failed: {(error or 'unknown error')[:200]}"

    # --- Signals ---

    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("received signal %d", signum)
            self._stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except ValueError:
                # signal() only works on the main thread; harmless if we're not on it.
                pass
