from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mikrotik_minder_agent.backup import (
    BackupConfigError,
    BackupError,
    BackupRunner,
)
from mikrotik_minder_agent.config import (
    AgentConfig,
    BackupConfig,
    Defaults,
    DeviceConfig,
    ServerConfig,
)
from mikrotik_minder_agent.transports import TransportError


@dataclass
class FakeChannel:
    """Stub SSHTransport that records every command and produces a fake backup file."""

    contents: bytes = b"FAKE_BACKUP_BYTES"
    commands: list[tuple[str, float | None]] = field(default_factory=list)
    fail_save: bool = False
    fail_pull: bool = False

    def capture(self, command: str, *, timeout: float | None = None) -> str:
        self.commands.append((command, timeout))
        if self.fail_save and command.startswith("/system backup save"):
            raise TransportError("simulated save failure")
        return ""

    def pull_file(
        self,
        remote_path: str,
        local_path: Path,
        *,
        timeout: float | None = None,
    ) -> int:
        if self.fail_pull:
            raise TransportError(f"simulated pull failure for {remote_path}")
        local_path.write_bytes(self.contents)
        return len(self.contents)


def _config(
    tmp_path: Path,
    *,
    password: str = "s3cret",  # noqa: S107 - test fixture, password is fake
    retention: int = 3,
) -> AgentConfig:
    return AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(),
        devices=(
            DeviceConfig(name="rtr-01", address="1.1.1.1", username="u", password="p"),
        ),
        backup=BackupConfig(dir=str(tmp_path / "backups"), password=password, retention=retention),
    )


def test_cleanup_runs_even_when_save_fails(tmp_path: Path) -> None:
    """A save that fails *after* RouterOS created the file must still trigger the
    on-router `/file remove` cleanup, so artifacts don't accumulate on the device.
    (Regression: pre-fix the save raised before the cleanup try/finally.)"""
    cfg = _config(tmp_path)
    runner = BackupRunner(cfg)
    ch = FakeChannel(fail_save=True)
    with pytest.raises(BackupError, match="save failed"):
        runner.run(cfg.devices[0], channel=ch)
    assert any(cmd.startswith("/file remove") for cmd, _ in ch.commands)


def test_first_run_creates_file_and_reports_hash(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runner = BackupRunner(cfg)
    ch = FakeChannel(contents=b"hello world")
    result = runner.run(cfg.devices[0], channel=ch)

    assert Path(result.file_path).read_bytes() == b"hello world"
    assert result.size_bytes == 11
    assert len(result.sha256) == 64  # sha256 hex
    # Three commands: save, then (after pull) cleanup.
    save_cmds = [c for c, _ in ch.commands if c.startswith("/system backup save")]
    rm_cmds = [c for c, _ in ch.commands if c.startswith("/file remove")]
    assert len(save_cmds) == 1
    assert len(rm_cmds) == 1
    assert "encryption=aes-sha256" in save_cmds[0]
    assert 'password="s3cret"' in save_cmds[0]


def test_retention_prunes_older_files(tmp_path: Path) -> None:
    cfg = _config(tmp_path, retention=2)
    runner = BackupRunner(cfg)

    # Seed two old backup files so the very first real run already has neighbours.
    device_dir = tmp_path / "backups" / "rtr-01"
    device_dir.mkdir(parents=True)
    old_a = device_dir / "minder-rtr-01-20200101T000000Z.backup"
    old_b = device_dir / "minder-rtr-01-20200102T000000Z.backup"
    old_a.write_bytes(b"a")
    old_b.write_bytes(b"b")
    # Backdate so the new file is newest.
    import os
    os.utime(old_a, (1577836800, 1577836800))
    os.utime(old_b, (1577923200, 1577923200))

    result = runner.run(cfg.devices[0], channel=FakeChannel())
    assert result.retained == 2
    assert result.pruned == 1
    # The newest old + the just-saved one survive; the oldest is gone.
    assert not old_a.exists()
    assert old_b.exists()
    assert Path(result.file_path).exists()


def test_save_failure_does_not_leave_local_artifact(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runner = BackupRunner(cfg)
    ch = FakeChannel(fail_save=True)
    with pytest.raises(BackupError, match="save"):
        runner.run(cfg.devices[0], channel=ch)
    device_dir = tmp_path / "backups" / "rtr-01"
    assert not list(device_dir.glob("*.backup")) if device_dir.exists() else True


def test_pull_failure_still_attempts_remote_cleanup(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runner = BackupRunner(cfg)
    ch = FakeChannel(fail_pull=True)
    with pytest.raises(BackupError, match="pull"):
        runner.run(cfg.devices[0], channel=ch)
    # cleanup attempt fires even on pull failure
    rm_cmds = [c for c, _ in ch.commands if c.startswith("/file remove")]
    assert len(rm_cmds) == 1


def test_password_with_double_quote_is_rejected(tmp_path: Path) -> None:
    cfg = _config(tmp_path, password='bad"password')
    with pytest.raises(BackupConfigError, match="double quote"):
        BackupRunner(cfg)


def test_runner_requires_backup_section() -> None:
    bare = AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(),
        devices=(
            DeviceConfig(name="a", address="1.1.1.1", username="u", password="p"),
        ),
    )
    with pytest.raises(BackupConfigError):
        BackupRunner(bare)
