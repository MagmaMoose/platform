"""Run ``/export`` on a device, commit the result to Git, summarise the diff.

SSH only for v1 — the API surface for `/export` is awkward (it's a CLI command,
not a structured RPC), and SSH is universally available on RouterOS.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from .config import AgentConfig, DeviceConfig, GitConfig
from .gitrepo import CommitResult, GitError, GitPushError, GitRepo
from .normalise import normalise_export
from .transports import TransportError
from .transports.ssh import SSHTransport

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportResult:
    started_at: int
    finished_at: int
    bytes_captured: int
    changed: bool
    commit_sha: str | None
    lines_added: int
    lines_removed: int
    relative_path: str
    pushed: bool = False           # True when a push was attempted AND succeeded
    push_skipped: bool = True      # True when no remote was configured or --skip-push was set
    push_error: str | None = None  # Set when a push was attempted and failed

    @property
    def duration_seconds(self) -> int:
        return self.finished_at - self.started_at


class _Capture(Protocol):
    def capture(self, command: str, *, timeout: float | None = ...) -> str: ...


class ExportRunner:
    """Encapsulates the export pipeline for one config repo."""

    def __init__(self, agent_config: AgentConfig) -> None:
        if agent_config.git is None:
            raise ExportConfigError(
                "exports require a 'git' section in config (with repo path)",
            )
        self._cfg = agent_config
        self._git_cfg: GitConfig = agent_config.git
        self._repo = GitRepo(
            self._git_cfg.repo,
            author_name=self._git_cfg.author_name,
            author_email=self._git_cfg.author_email,
        )

    def run(
        self,
        device: DeviceConfig,
        *,
        capture: _Capture | None = None,
        command: str = "/export",
        skip_push: bool = False,
    ) -> ExportResult:
        """Capture ``/export``, normalise, commit if changed, return the result."""
        started = int(time.time())
        client = capture or SSHTransport(device, self._cfg.defaults)
        try:
            raw = client.capture(command, timeout=self._cfg.defaults.export_timeout_seconds)
        except TransportError as exc:
            raise ExportError(f"capture failed: {exc}") from exc

        normalised = normalise_export(raw)
        rel = f"devices/{device.name}/exports/latest.rsc"
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
        try:
            commit = self._repo.write_and_commit(
                rel,
                normalised,
                message=f"{device.name}: export {ts}",
            )
        except GitError as exc:
            raise ExportError(f"git commit failed: {exc}") from exc

        push_state = self._maybe_push(commit_made=commit is not None, skip=skip_push)
        return _result(started, normalised, rel, commit, push_state)

    def _maybe_push(self, *, commit_made: bool, skip: bool) -> _PushState:
        """Push to the configured remote if commit_made + remote configured + not skipped."""
        remote = self._git_cfg.remote
        if skip or remote is None or not remote.push or not commit_made:
            return _PushState(skipped=True)
        try:
            self._repo.push(
                remote.url,
                branch=remote.branch,
                ssh_key_path=remote.ssh_key_path,
                token=remote.token,
                known_hosts_path=remote.known_hosts_path,
            )
        except GitPushError as exc:
            log.warning("export push to %s failed: %s", _safe_url(remote.url), exc)
            return _PushState(error=str(exc))
        return _PushState(pushed=True)


@dataclass(frozen=True)
class _PushState:
    pushed: bool = False
    skipped: bool = False
    error: str | None = None


def _safe_url(url: str) -> str:
    """Strip userinfo from a URL when logging (in case a token sneaks in)."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    if parts.username or parts.password:
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return url


class ExportError(RuntimeError):
    """Raised when an export run cannot complete."""


class ExportConfigError(ExportError):
    """Raised when the agent config does not enable exports."""


def _result(
    started: int,
    normalised: str,
    rel: str,
    commit: CommitResult | None,
    push: _PushState,
) -> ExportResult:
    finished = int(time.time())
    base = {
        "started_at": started,
        "finished_at": finished,
        "bytes_captured": len(normalised),
        "relative_path": rel,
        "pushed": push.pushed,
        "push_skipped": push.skipped,
        "push_error": push.error,
    }
    if commit is None:
        return ExportResult(
            **base,
            changed=False,
            commit_sha=None,
            lines_added=0,
            lines_removed=0,
        )
    return ExportResult(
        **base,
        changed=True,
        commit_sha=commit.sha,
        lines_added=commit.lines_added,
        lines_removed=commit.lines_removed,
    )
