"""Tests for the operator-command dispatcher in ``commands.py``.

These exercise the public ``execute_command`` entry point with the per-kind
collaborators (export/backup runners, SSH transport, ``apply_update``) stubbed
out via monkeypatching. The goal is to pin down the contract Copilot called
out in PR #15: each kind dispatches to the right runner, and every code path
ends in either a ``succeeded`` or ``failed`` ``report_command_result`` call —
plus a parallel ``send_job`` mirror for the kinds that show up in the timeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from mikrotik_minder_agent import commands as commands_module
from mikrotik_minder_agent.apply import ApplyAborted, ApplyError, ApplyResult, ResourceSnapshot
from mikrotik_minder_agent.backup import BackupError, BackupResult
from mikrotik_minder_agent.commands import execute_command
from mikrotik_minder_agent.config import AgentConfig, Defaults, DeviceConfig, ServerConfig
from mikrotik_minder_agent.export import ExportError, ExportResult
from mikrotik_minder_agent.minder import CommandRef, JobReport
from mikrotik_minder_agent.transports import TransportError

DEVICE = DeviceConfig(
    name="core-rtr-01",
    address="10.0.0.1",
    username="admin",
    password="secret",
)

CONFIG = AgentConfig(
    server=ServerConfig(url="https://minder.example", agent_token="mtm_test"),
    defaults=Defaults(),
    devices=(DEVICE,),
)


@dataclass
class FakeMinder:
    """Captures report_command_result + send_job calls for assertions."""

    results: list[dict[str, Any]] = field(default_factory=list)
    jobs: list[JobReport] = field(default_factory=list)

    def report_command_result(
        self,
        cmd_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        artifact: str | None = None,
    ) -> None:
        self.results.append(
            {"cmd_id": cmd_id, "status": status, "result": result, "artifact": artifact},
        )

    def send_job(self, job: JobReport) -> str:
        self.jobs.append(job)
        return "job_x"


def _ok_export_result() -> ExportResult:
    return ExportResult(
        started_at=1000,
        finished_at=1005,
        bytes_captured=1234,
        changed=True,
        commit_sha="abc1234",
        lines_added=3,
        lines_removed=1,
        relative_path="devices/core-rtr-01/exports/latest.rsc",
        pushed=True,
        push_skipped=False,
        push_error=None,
    )


def _ok_backup_result() -> BackupResult:
    return BackupResult(
        started_at=1000,
        finished_at=1010,
        file_path="/data/backups/core-rtr-01/latest.backup",
        file_name="latest.backup",
        size_bytes=98765,
        sha256="deadbeef" * 8,
        retained=5,
        pruned=1,
    )


def _ok_apply_result() -> ApplyResult:
    before = ResourceSnapshot(
        version="7.18.2",
        free_hdd_space="46.2GiB",
        identity="core-rtr-01",
        uptime="1d",
        board_name="CCR2004",
    )
    after = ResourceSnapshot(
        version="7.22.3",
        free_hdd_space="45.1GiB",
        identity="core-rtr-01",
        uptime="2m",
        board_name="CCR2004",
    )
    return ApplyResult(
        started_at=2000,
        finished_at=2700,
        ticket="cmd:abc",
        before=before,
        after=after,
        downtime_seconds=600,
    )


# --- backup ---------------------------------------------------------------


class _Runner:
    def __init__(self, result: Any | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[DeviceConfig] = []
        self.uploaders: list[Any] = []

    def run(self, device: DeviceConfig, *, uploader: Any | None = None) -> Any:
        # BackupRunner.run gained an `uploader` kwarg so the agent can stream
        # the encrypted body to the worker's R2 bucket. ExportRunner.run does
        # NOT take this kwarg — but tests use a single fake for both kinds,
        # so we accept and ignore it on the export path.
        self.calls.append(device)
        self.uploaders.append(uploader)
        if self._error is not None:
            raise self._error
        return self._result


def test_backup_success_reports_succeeded_and_mirrors_job() -> None:
    minder = FakeMinder()
    runner = _Runner(result=_ok_backup_result())

    execute_command(
        CommandRef(id="cmd1", device="core-rtr-01", kind="backup", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=runner,
    )

    assert len(runner.calls) == 1
    # Dispatcher must pass the MinderClient as the uploader so the encrypted
    # body lands in R2 alongside the local PVC copy.
    assert runner.uploaders == [minder]
    assert minder.results[-1]["status"] == "succeeded"
    assert minder.results[-1]["result"]["size_bytes"] == 98765
    assert minder.results[-1]["artifact"] is None
    # Parallel jobs row so the run shows up in the device timeline.
    assert len(minder.jobs) == 1
    assert minder.jobs[0].kind == "backup"
    assert minder.jobs[0].status == "success"


def test_backup_error_reports_failed_and_mirrors_failure_job() -> None:
    minder = FakeMinder()
    runner = _Runner(error=BackupError("sftp pull blew up"))

    execute_command(
        CommandRef(id="cmd1", device="core-rtr-01", kind="backup", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=runner,
    )

    assert minder.results[-1]["status"] == "failed"
    assert "sftp pull blew up" in minder.results[-1]["result"]["error"]
    assert len(minder.jobs) == 1
    assert minder.jobs[0].status == "failed"


def test_backup_with_no_runner_reports_failed_without_calling_anyone() -> None:
    minder = FakeMinder()

    execute_command(
        CommandRef(id="cmd1", device="core-rtr-01", kind="backup", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "failed"
    assert "not configured" in minder.results[-1]["result"]["error"]
    assert minder.jobs == []


# --- export ---------------------------------------------------------------


def test_export_changed_reports_succeeded_with_drift_job() -> None:
    minder = FakeMinder()
    runner = _Runner(result=_ok_export_result())

    execute_command(
        CommandRef(id="cmd2", device="core-rtr-01", kind="export", params={}),
        CONFIG,
        minder=minder,
        exporter=runner,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "succeeded"
    assert minder.results[-1]["result"]["changed"] is True
    # When something changed AND the push went through, the timeline job is
    # `drift` with `warning` status (so it shows up but doesn't page).
    assert minder.jobs[0].kind == "drift"
    assert minder.jobs[0].status == "warning"


def test_export_push_failure_reports_failed() -> None:
    minder = FakeMinder()
    runner = _Runner(
        result=ExportResult(
            started_at=1000,
            finished_at=1002,
            bytes_captured=100,
            changed=True,
            commit_sha="abc",
            lines_added=1,
            lines_removed=0,
            relative_path="devices/core-rtr-01/exports/latest.rsc",
            pushed=False,
            push_skipped=False,
            push_error="auth denied",
        ),
    )

    execute_command(
        CommandRef(id="cmd2", device="core-rtr-01", kind="export", params={}),
        CONFIG,
        minder=minder,
        exporter=runner,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "failed"
    assert minder.jobs[0].status == "failed"


def test_export_capture_error_reports_failed() -> None:
    minder = FakeMinder()
    runner = _Runner(error=ExportError("ssh died"))

    execute_command(
        CommandRef(id="cmd2", device="core-rtr-01", kind="export", params={}),
        CONFIG,
        minder=minder,
        exporter=runner,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "failed"
    assert "ssh died" in minder.results[-1]["result"]["error"]


# --- update_apply ---------------------------------------------------------


def test_update_apply_now_calls_apply_update_and_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minder = FakeMinder()
    monkeypatch.setattr(
        commands_module,
        "apply_update",
        lambda *_a, **_kw: _ok_apply_result(),
    )

    execute_command(
        CommandRef(id="cmd3", device="core-rtr-01", kind="update_apply", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "succeeded"
    assert minder.results[-1]["result"]["before_version"] == "7.18.2"
    assert minder.results[-1]["result"]["after_version"] == "7.22.3"
    assert minder.jobs[0].kind == "update_apply"
    assert minder.jobs[0].status == "success"


def test_update_apply_aborted_reports_aborted_pre_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minder = FakeMinder()

    def _abort(*_a: object, **_kw: object) -> ApplyResult:
        raise ApplyAborted("free space too low")

    monkeypatch.setattr(commands_module, "apply_update", _abort)

    execute_command(
        CommandRef(id="cmd3", device="core-rtr-01", kind="update_apply", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "failed"
    assert minder.results[-1]["result"]["aborted_pre_install"] is True


def test_update_apply_runtime_error_reports_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    minder = FakeMinder()

    def _boom(*_a: object, **_kw: object) -> ApplyResult:
        raise ApplyError("reboot timed out")

    monkeypatch.setattr(commands_module, "apply_update", _boom)

    execute_command(
        CommandRef(id="cmd3", device="core-rtr-01", kind="update_apply", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "failed"
    # No aborted_pre_install marker on non-abort failures.
    assert "aborted_pre_install" not in minder.results[-1]["result"]


def test_update_apply_download_only_captures_and_returns_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minder = FakeMinder()

    class _SSH:
        def __init__(self, *_a: object, **_kw: object) -> None:
            self.called: list[str] = []

        def capture(self, command: str, *, timeout: float | None = None) -> str:
            self.called.append(command)
            return "downloaded ok"

    monkeypatch.setattr(commands_module, "SSHTransport", _SSH)

    execute_command(
        CommandRef(
            id="cmd3",
            device="core-rtr-01",
            kind="update_apply",
            params={"mode": "download_only"},
        ),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "succeeded"
    assert minder.results[-1]["result"]["mode"] == "download_only"
    assert "downloaded ok" in minder.results[-1]["result"]["output"]
    # download_only does NOT mirror a jobs row — it's a check, not a maintenance event.
    assert minder.jobs == []


# --- sensitive_export -----------------------------------------------------


def test_sensitive_export_returns_artifact_with_normalised_newlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minder = FakeMinder()

    class _SSH:
        def __init__(self, *_a: object, **_kw: object) -> None:
            pass

        def capture(self, command: str, *, timeout: float | None = None) -> str:
            assert command == "/export show-sensitive"
            return "# sensitive\r\n/user add password=hunter2\r\n"

    monkeypatch.setattr(commands_module, "SSHTransport", _SSH)

    execute_command(
        CommandRef(id="cmd4", device="core-rtr-01", kind="sensitive_export", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=None,
    )

    out = minder.results[-1]
    assert out["status"] == "succeeded"
    # CRLF normalised to LF, and the body is delivered as an artifact (one-shot).
    assert out["artifact"] == "# sensitive\n/user add password=hunter2\n"
    assert "\r\n" not in out["artifact"]
    assert out["result"] == {"bytes": len(out["artifact"])}


def test_sensitive_export_capture_failure_reports_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minder = FakeMinder()

    class _SSH:
        def __init__(self, *_a: object, **_kw: object) -> None:
            pass

        def capture(self, _command: str, *, timeout: float | None = None) -> str:
            raise TransportError("ssh blew up")

    monkeypatch.setattr(commands_module, "SSHTransport", _SSH)

    execute_command(
        CommandRef(id="cmd4", device="core-rtr-01", kind="sensitive_export", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "failed"
    assert "ssh blew up" in minder.results[-1]["result"]["error"]
    assert minder.results[-1]["artifact"] is None


# --- dispatch edge cases --------------------------------------------------


def test_unknown_device_reports_failed_without_running_anything() -> None:
    minder = FakeMinder()
    runner = _Runner(result=_ok_backup_result())

    execute_command(
        CommandRef(id="cmd5", device="ghost", kind="backup", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=runner,
    )

    assert minder.results[-1]["status"] == "failed"
    assert "ghost" in minder.results[-1]["result"]["error"]
    assert runner.calls == []
    assert minder.jobs == []


def test_unknown_kind_reports_failed() -> None:
    minder = FakeMinder()

    execute_command(
        CommandRef(id="cmd6", device="core-rtr-01", kind="weird", params={}),
        CONFIG,
        minder=minder,
        exporter=None,
        backup_runner=None,
    )

    assert minder.results[-1]["status"] == "failed"
    assert "unknown command kind" in minder.results[-1]["result"]["error"]
