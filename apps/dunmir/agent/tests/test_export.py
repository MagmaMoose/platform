from __future__ import annotations

from pathlib import Path

import pytest

from mikrotik_minder_agent.config import (
    AgentConfig,
    Defaults,
    DeviceConfig,
    GitConfig,
    ServerConfig,
)
from mikrotik_minder_agent.export import ExportConfigError, ExportRunner


class FakeCapture:
    """Stand-in for SSHTransport that returns canned `/export` text."""

    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[str, float | None]] = []

    def capture(self, command: str, *, timeout: float | None = None) -> str:
        self.calls.append((command, timeout))
        return self.output


def _config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(export_interval_seconds=3600),
        devices=(
            DeviceConfig(name="rtr-01", address="1.1.1.1", username="u", password="p"),
        ),
        git=GitConfig(repo=str(tmp_path / "configs")),
    )


def test_runner_requires_git_section() -> None:
    bare = AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(),
        devices=(
            DeviceConfig(name="a", address="1.1.1.1", username="u", password="p"),
        ),
    )
    with pytest.raises(ExportConfigError):
        ExportRunner(bare)


def test_first_run_commits_and_reports_change(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runner = ExportRunner(cfg)
    fake = FakeCapture(
        "\n".join(
            [
                "# 2024-03-15 14:23:45 by RouterOS 7.18.2",
                "/system identity",
                'set name="rtr-01"',
                "",
            ],
        ),
    )
    result = runner.run(cfg.devices[0], capture=fake)

    assert result.changed is True
    assert result.commit_sha is not None and len(result.commit_sha) >= 7
    assert result.lines_added > 0
    # Volatile header line stripped.
    body = (tmp_path / "configs" / result.relative_path).read_text()
    assert "by RouterOS" not in body
    assert body.startswith("/system identity")
    # Capture got the right command + timeout.
    assert fake.calls == [("/export", cfg.defaults.export_timeout_seconds)]


def test_second_run_unchanged_returns_no_commit(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runner = ExportRunner(cfg)
    output = "# 2024-03-15 14:23:45 by RouterOS 7.18.2\n/system identity\nset name=\"rtr-01\"\n"

    first = runner.run(cfg.devices[0], capture=FakeCapture(output))
    assert first.changed is True
    second = runner.run(cfg.devices[0], capture=FakeCapture(output))
    assert second.changed is False
    assert second.commit_sha is None
    assert second.lines_added == 0
    assert second.lines_removed == 0


def test_volatile_header_change_does_not_produce_drift(tmp_path: Path) -> None:
    """The header stripping is the whole point — a new timestamp must not cause a commit."""
    cfg = _config(tmp_path)
    runner = ExportRunner(cfg)
    monday = "# 2024-03-15 14:23:45 by RouterOS 7.18.2\n/system identity\nset name=\"rtr-01\"\n"
    tuesday = "# 2024-03-16 09:11:02 by RouterOS 7.18.2\n/system identity\nset name=\"rtr-01\"\n"

    assert runner.run(cfg.devices[0], capture=FakeCapture(monday)).changed is True
    assert runner.run(cfg.devices[0], capture=FakeCapture(tuesday)).changed is False


def test_real_config_change_produces_drift(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runner = ExportRunner(cfg)
    before = "# 2024-03-15 14:23:45 by RouterOS 7.18.2\n/system identity\nset name=\"old\"\n"
    after = "# 2024-03-16 09:11:02 by RouterOS 7.18.2\n/system identity\nset name=\"new\"\n"

    runner.run(cfg.devices[0], capture=FakeCapture(before))
    drift = runner.run(cfg.devices[0], capture=FakeCapture(after))

    assert drift.changed is True
    assert drift.lines_added >= 1
    assert drift.lines_removed >= 1
