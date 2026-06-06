"""ExportRunner ↔ remote-push integration tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mikrotik_minder_agent.config import (
    AgentConfig,
    Defaults,
    DeviceConfig,
    GitConfig,
    GitRemoteConfig,
    ServerConfig,
)
from mikrotik_minder_agent.export import ExportRunner


class FakeCapture:
    def __init__(self, output: str) -> None:
        self.output = output

    def capture(self, command: str, *, timeout: float | None = None) -> str:
        return self.output


def _bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    return remote


def _cfg(tmp_path: Path, *, remote_url: str | None) -> AgentConfig:
    git = GitConfig(
        repo=str(tmp_path / "configs"),
        remote=GitRemoteConfig(url=remote_url, branch="main") if remote_url else None,
    )
    return AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(),
        devices=(DeviceConfig(name="rtr", address="1.1.1.1", username="u", password="p"),),
        git=git,
    )


CONFIG_BEFORE = (
    "# 2024-03-15 14:23:45 by RouterOS 7.18.2\n"
    "/ip address\n"
    "add address=10/24\n"
)
CONFIG_AFTER = (
    "# 2024-03-16 09:11:02 by RouterOS 7.18.2\n"
    "/ip address\n"
    "add address=10/24\n"
    "add address=11/24\n"
)


def test_push_happens_after_a_real_change(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    cfg = _cfg(tmp_path, remote_url=f"file://{remote}")
    runner = ExportRunner(cfg)

    result = runner.run(cfg.devices[0], capture=FakeCapture(CONFIG_BEFORE))
    assert result.changed is True
    assert result.pushed is True
    assert result.push_skipped is False
    assert result.push_error is None

    # remote now has main
    out = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        check=True, capture_output=True, text=True,
    )
    assert out.stdout.strip() == result.commit_sha


def test_no_change_means_no_push(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    cfg = _cfg(tmp_path, remote_url=f"file://{remote}")
    runner = ExportRunner(cfg)
    runner.run(cfg.devices[0], capture=FakeCapture(CONFIG_BEFORE))

    result = runner.run(cfg.devices[0], capture=FakeCapture(CONFIG_BEFORE))
    assert result.changed is False
    assert result.pushed is False
    # no_change → no push attempted → "skipped" rather than "pushed"
    assert result.push_skipped is True


def test_skip_push_overrides_remote_config(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    cfg = _cfg(tmp_path, remote_url=f"file://{remote}")
    runner = ExportRunner(cfg)

    result = runner.run(cfg.devices[0], capture=FakeCapture(CONFIG_BEFORE), skip_push=True)
    assert result.changed is True
    assert result.pushed is False
    assert result.push_skipped is True
    # remote stays empty
    rev = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        capture_output=True, text=True,
    )
    assert rev.returncode != 0  # main doesn't exist yet


def test_push_failure_records_error_but_keeps_local_commit(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, remote_url="file:///no/such/remote.git")
    runner = ExportRunner(cfg)

    result = runner.run(cfg.devices[0], capture=FakeCapture(CONFIG_BEFORE))
    assert result.changed is True
    assert result.commit_sha is not None  # local commit ok
    assert result.pushed is False
    assert result.push_skipped is False
    assert result.push_error is not None
    assert "git push" in result.push_error.lower() or "no such" in result.push_error.lower()

    # local HEAD resolves — the operator can still inspect the diff
    rev = subprocess.run(
        ["git", "-C", str(tmp_path / "configs"), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    assert rev.stdout.strip() == result.commit_sha


def test_no_remote_configured_is_local_only(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, remote_url=None)
    runner = ExportRunner(cfg)
    result = runner.run(cfg.devices[0], capture=FakeCapture(CONFIG_BEFORE))
    assert result.changed is True
    assert result.pushed is False
    assert result.push_skipped is True


def test_remote_push_false_disables_push_without_removing_remote(tmp_path: Path) -> None:
    """`push: false` in config pauses pushing without deleting the remote section."""
    remote = _bare_remote(tmp_path)
    git_cfg = GitConfig(
        repo=str(tmp_path / "configs"),
        remote=GitRemoteConfig(url=f"file://{remote}", branch="main", push=False),
    )
    cfg = AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(),
        devices=(DeviceConfig(name="rtr", address="1.1.1.1", username="u", password="p"),),
        git=git_cfg,
    )
    runner = ExportRunner(cfg)
    result = runner.run(cfg.devices[0], capture=FakeCapture(CONFIG_BEFORE))
    assert result.changed is True
    assert result.pushed is False
    assert result.push_skipped is True
    # remote unchanged
    rev = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        capture_output=True, text=True,
    )
    assert rev.returncode != 0
