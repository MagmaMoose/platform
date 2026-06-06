from __future__ import annotations

import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mikrotik_minder_agent.apply import (
    ApplyAborted,
    apply_update,
    find_recent_backup,
    parse_free_space_mib,
)
from mikrotik_minder_agent.config import (
    AgentConfig,
    BackupConfig,
    Defaults,
    DeviceConfig,
    ServerConfig,
)

# Fixture strings; trailing newline matters for kv parsing.
RES_OK = textwrap.dedent(
    """
    version: 7.18.2 (stable)
    free-hdd-space: 46.2GiB
    uptime: 1d
    """,
).lstrip()

RES_LOW_SPACE = "version: 7.18.2\nfree-hdd-space: 50MiB\n"

UPD_UP_TO_DATE = textwrap.dedent(
    """
    channel: stable
    installed-version: 7.18.2
    latest-version: 7.18.2
    status: System is already up to date
    """,
).lstrip()

UPD_AVAILABLE = textwrap.dedent(
    """
    channel: stable
    installed-version: 7.18.2
    latest-version: 7.22.3
    status: New version is available
    """,
).lstrip()


@dataclass
class FakeChannel:
    """Cycles canned responses keyed by command prefix."""

    responses: dict[str, list[str]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def capture(self, command: str, *, timeout: float | None = None) -> str:
        self.calls.append(command)
        for prefix, queue in self.responses.items():
            if command.startswith(prefix):
                if not queue:
                    return ""
                return queue.pop(0) if len(queue) > 1 else queue[0]
        return ""


def _cfg(tmp_path: Path) -> AgentConfig:
    backup = BackupConfig(
        dir=str(tmp_path / "backups"),
        password="pp",
        retention=3,
    )
    return AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(connect_timeout_seconds=1.0),
        devices=(
            DeviceConfig(name="rtr", address="1.1.1.1", username="u", password="p"),
        ),
        backup=backup,
    )


def test_parse_free_space_mib_gib() -> None:
    assert parse_free_space_mib("46.2GiB") == pytest.approx(46.2 * 1024)


def test_parse_free_space_mib_mib() -> None:
    assert parse_free_space_mib("739.6MiB") == pytest.approx(739.6)


def test_parse_free_space_mib_garbage_returns_none() -> None:
    assert parse_free_space_mib("not a size") is None
    assert parse_free_space_mib(None) is None


def test_find_recent_backup_skips_old_files(tmp_path: Path) -> None:
    d = tmp_path / "backups" / "rtr"
    d.mkdir(parents=True)
    old = d / "minder-rtr-old.backup"
    fresh = d / "minder-rtr-new.backup"
    old.write_bytes(b"a")
    fresh.write_bytes(b"b")
    now = time.time()
    import os
    os.utime(old, (now - 7200, now - 7200))  # 2h old
    os.utime(fresh, (now - 60, now - 60))    # 1m old

    found = find_recent_backup(tmp_path / "backups", "rtr", max_age_seconds=3600, now=now)
    assert found == fresh


def test_find_recent_backup_returns_none_when_all_stale(tmp_path: Path) -> None:
    d = tmp_path / "backups" / "rtr"
    d.mkdir(parents=True)
    p = d / "old.backup"
    p.write_bytes(b"a")
    import os
    os.utime(p, (1, 1))
    assert find_recent_backup(tmp_path / "backups", "rtr", max_age_seconds=60) is None


def test_apply_requires_ticket(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    with pytest.raises(ApplyAborted, match="TICKET"):
        apply_update(cfg, cfg.devices[0], ticket="", channel=FakeChannel())


def test_apply_aborts_when_no_update_available(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    ch = FakeChannel(responses={
        "/system resource print": [RES_OK],
        "/system package update check-for-updates": [UPD_UP_TO_DATE],
    })
    with pytest.raises(ApplyAborted, match="no update available"):
        apply_update(cfg, cfg.devices[0], ticket="TICKET-1", channel=ch)


def test_apply_aborts_when_no_recent_backup(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    ch = FakeChannel(responses={
        "/system resource print": [RES_OK],
        "/system package update check-for-updates": [UPD_AVAILABLE],
    })
    with pytest.raises(ApplyAborted, match="no backup"):
        apply_update(cfg, cfg.devices[0], ticket="TICKET-1", channel=ch)


def test_apply_aborts_when_insufficient_free_space(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    ch = FakeChannel(responses={"/system resource print": [RES_LOW_SPACE]})
    with pytest.raises(ApplyAborted, match="MiB free"):
        apply_update(
            cfg, cfg.devices[0], ticket="TICKET-1", channel=ch,
            min_free_mib=100.0,
        )


def test_apply_skip_backup_check_allows_run_without_backup(tmp_path: Path) -> None:
    """The point is the backup precondition is bypassable. We can't get further
    than the reboot wait because the stub channel can't simulate a real router
    going offline and coming back, so we accept any non-abort exception."""
    cfg = _cfg(tmp_path)
    ch = FakeChannel(responses={
        "/system resource print": [RES_OK],
        "/system package update check-for-updates": [UPD_AVAILABLE],
    })
    from mikrotik_minder_agent.apply import ApplyError, ApplyTimedOut

    with pytest.raises((ApplyError, ApplyTimedOut)) as excinfo:
        apply_update(
            cfg, cfg.devices[0], ticket="T", channel=ch,
            require_backup=False,
            max_wait_seconds=2,
        )
    # the error must not be a missing-backup abort
    assert "backup" not in str(excinfo.value).lower()
