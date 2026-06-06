"""Encrypted binary backup pipeline.

Flow per device:

1. ``/system backup save name=<name> password=<bp> encryption=aes-sha256`` on the router.
2. SFTP-pull ``<name>.backup`` to ``<backup.dir>/<device>/<name>.backup``.
3. ``/file remove [find name=<name>.backup]`` on the router to clear the artifact.
4. Hash the local file (sha256) and rotate older files per retention policy.

The router-side ``password=…`` does end up on the SSH command channel, so RouterOS
may log the literal command to its system log. The agent itself never logs the
password. Operators who want to keep it out of router logs entirely should
consider the API transport (future) or set up command-history filtering on the
device. For homelab v1 this trade-off is documented in the README.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import AgentConfig, BackupConfig, DeviceConfig
from .transports import TransportError
from .transports.ssh import SSHTransport

log = logging.getLogger(__name__)

# Characters that would break RouterOS string parsing inside a quoted argument.
_BAD_PASSWORD_CHARS = '"\\'  # noqa: S105 - this is a constant, not a credential


class BackupError(RuntimeError):
    """Raised when a backup run cannot complete."""


class BackupConfigError(BackupError):
    """Raised when the agent config does not enable backups."""


@dataclass(frozen=True)
class BackupResult:
    started_at: int
    finished_at: int
    file_path: str
    file_name: str
    size_bytes: int
    sha256: str
    retained: int   # files remaining after retention sweep
    pruned: int     # files removed during retention sweep
    # Control-plane upload status — the .backup body is also streamed to the
    # worker's R2 bucket so the Pro UI can download it later. The local PVC
    # copy is still authoritative; an upload failure leaves a warning on the
    # job but does NOT fail the backup itself.
    uploaded_id: str | None = None     # backup_files.id once upload completes
    upload_skipped: bool = True        # True when no MinderClient was provided
    upload_error: str | None = None    # set on transient/4xx/5xx upload failures


class _BackupChannel(Protocol):
    """Just enough of SSHTransport to back-up a device. Used for test injection."""

    def capture(self, command: str, *, timeout: float | None = ...) -> str: ...
    def pull_file(
        self,
        remote_path: str,
        local_path: Path,
        *,
        timeout: float | None = ...,
    ) -> int: ...


class _BackupUploader(Protocol):
    """Just enough of MinderClient to ship a backup body upstream."""

    def upload_backup(
        self,
        device: str,
        file_path: Path,
        *,
        sha256: str | None = ...,
    ) -> str: ...


class BackupRunner:
    """Run encrypted binary backups and keep a rotating local archive."""

    def __init__(self, config: AgentConfig) -> None:
        if config.backup is None:
            raise BackupConfigError(
                "backups require a 'backup' section in config (dir + password_env)",
            )
        self._cfg = config
        self._bcfg: BackupConfig = config.backup
        if any(c in self._bcfg.password for c in _BAD_PASSWORD_CHARS):
            raise BackupConfigError(
                "backup.password must not contain a double quote or backslash; "
                "RouterOS cannot parse them inside quoted arguments",
            )
        self._root = Path(self._bcfg.dir).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    # --- Public API ---

    def run(
        self,
        device: DeviceConfig,
        *,
        channel: _BackupChannel | None = None,
        uploader: _BackupUploader | None = None,
    ) -> BackupResult:
        started = int(time.time())
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(started))
        name = f"minder-{device.name}-{ts}"
        on_device = f"{name}.backup"
        local_dir = self._root / device.name
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / on_device

        ssh = channel or SSHTransport(device, self._cfg.defaults)
        save_timeout = self._cfg.defaults.backup_save_timeout_seconds
        pull_timeout = self._cfg.defaults.backup_pull_timeout_seconds

        # Steps 1-3 share one try/finally so the on-router artifact is always
        # cleaned up — even if `save` times out *after* RouterOS created the
        # file. A `/file remove` for a name that was never created is a no-op.
        try:
            # 1. Create the backup on the router.
            try:
                ssh.capture(
                    f'/system backup save name="{name}" '
                    f'password="{self._bcfg.password}" encryption=aes-sha256',
                    timeout=save_timeout,
                )
            except TransportError as exc:
                raise BackupError(f"backup save failed: {exc}") from exc

            # 2. SFTP-pull the .backup file off the router.
            try:
                ssh.pull_file(on_device, local_path, timeout=pull_timeout)
            except TransportError as exc:
                raise BackupError(f"backup pull failed: {exc}") from exc
        finally:
            # 3. Always try to clean up the on-device file (after save- or pull-failure too).
            try:
                ssh.capture(
                    f'/file remove [find name="{on_device}"]',
                    timeout=self._cfg.defaults.connect_timeout_seconds + 5,
                )
            except TransportError as exc:
                log.warning(
                    "device %s: backup cleanup failed (file may still be on router): %s",
                    device.name,
                    exc,
                )

        size = local_path.stat().st_size
        sha = _sha256(local_path)
        pruned = self._rotate(local_dir, retain=self._bcfg.retention)
        retained = len(list(local_dir.glob("*.backup")))

        # Stream the encrypted body to R2 via the worker. We do this BEFORE
        # the return so the job that's about to be posted can carry the
        # backup_id. Failures are non-fatal: the PVC copy is authoritative.
        uploaded_id: str | None = None
        upload_skipped = uploader is None
        upload_error: str | None = None
        if uploader is not None:
            try:
                uploaded_id = uploader.upload_backup(device.name, local_path, sha256=sha)
            except Exception as exc:  # broad: upload is non-fatal, surfaced in result
                upload_error = str(exc)
                log.warning(
                    "device %s: backup upload failed (%s); local copy at %s",
                    device.name, exc, local_path,
                )

        return BackupResult(
            started_at=started,
            finished_at=int(time.time()),
            file_path=str(local_path),
            file_name=on_device,
            size_bytes=size,
            sha256=sha,
            retained=retained,
            pruned=pruned,
            uploaded_id=uploaded_id,
            upload_skipped=upload_skipped,
            upload_error=upload_error,
        )

    # --- Internals ---

    @staticmethod
    def _rotate(directory: Path, *, retain: int) -> int:
        files = sorted(directory.glob("*.backup"), key=lambda p: p.stat().st_mtime, reverse=True)
        stale = files[retain:]
        for f in stale:
            try:
                f.unlink()
            except OSError as exc:  # pragma: no cover - rare
                log.warning("could not prune %s: %s", f, exc)
        return len(stale)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_summary(result: BackupResult) -> str:
    """One-line job summary suitable for the dashboard."""
    kb = result.size_bytes / 1024.0
    return (
        f"backup ok · {kb:.1f} KiB · sha256 {result.sha256[:12]}… · "
        f"{result.retained} retained ({result.pruned} pruned)"
    )
