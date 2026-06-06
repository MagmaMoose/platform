"""Thin wrapper around the ``git`` CLI for export history.

We shell out instead of using libgit2/pygit2 to avoid a native dependency. The
agent already has paramiko + cryptography pulled in via SSH; one less wheel to
worry about on ARM homelab boxes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class GitError(RuntimeError):
    """Raised when a git command fails."""


class GitPushError(GitError):
    """Raised specifically when a push to the remote fails.

    The local commit succeeded; only the off-site mirror is behind.
    """


_REMOTE_NAME = "minder-remote"


def _is_ssh_style(url: str) -> bool:
    """True for ``git@host:org/repo.git`` and ``ssh://...`` URLs."""
    non_ssh_prefixes = ("http://", "https://", "file://", "/")
    return url.startswith("ssh://") or (
        ":" in url and not url.startswith(non_ssh_prefixes)
    )


def _maybe_inject_token(url: str, token: str | None) -> str:
    """For HTTPS URLs with a token, return ``https://x-access-token:<TOKEN>@host/...``.

    SSH-style URLs and file:// URLs are returned unchanged; auth happens via
    ``GIT_SSH_COMMAND`` for the former and ambient FS perms for the latter.
    """
    if not token:
        return url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return url  # not HTTPS — token doesn't apply
    netloc = f"x-access-token:{token}@{parts.hostname or ''}"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@dataclass(frozen=True)
class CommitResult:
    sha: str
    lines_added: int
    lines_removed: int
    files_changed: int

    @property
    def total_changes(self) -> int:
        return self.lines_added + self.lines_removed


class GitRepo:
    """A local git repo used to store exported router configs.

    Lazily initialises the directory on the first commit so operators don't
    have to bootstrap anything beyond pointing the agent at a path.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        author_name: str = "mikrotik-minder",
        author_email: str = "mikrotik-minder@localhost",
    ) -> None:
        git_path = shutil.which("git")
        if git_path is None:
            raise GitError("`git` not found on PATH")
        self._git = git_path  # resolved absolute path; satisfies subprocess hardening lints
        self.root = Path(root).expanduser().resolve()
        self._author_name = author_name
        self._author_email = author_email
        # The daemon shares ONE GitRepo across per-device threads. Serialise the
        # operations that touch the index / working tree so concurrent device
        # exports can't race on .git/index.lock or let one device's commit
        # swallow another's staged file. Re-entrant because write_and_commit
        # calls ensure_initialised while already holding it.
        self._commit_lock = threading.RLock()
        # A push doesn't touch the index, but two concurrent `git push` of the
        # same ref can hit remote ref-lock contention and raise a *false* push
        # error. Serialise pushes on their own lock so a slow push never blocks
        # a commit (and vice versa).
        self._push_lock = threading.Lock()

    # --- Public API ---

    def ensure_initialised(self) -> None:
        with self._commit_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            if not (self.root / ".git").exists():
                self._run(["init", "--initial-branch=main"])
                # Pin per-repo identity so commits don't pick up global git config.
                self._run(["config", "user.name", self._author_name])
                self._run(["config", "user.email", self._author_email])
                # Unattended exports must not block on commit/tag signing (e.g. when the
                # operator's global git config points at a GUI signer like 1Password).
                self._run(["config", "commit.gpgsign", "false"])
                self._run(["config", "tag.gpgsign", "false"])

    def push(
        self,
        url: str,
        *,
        branch: str = "main",
        ssh_key_path: str | None = None,
        token: str | None = None,
        known_hosts_path: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        """Push ``branch`` to ``url`` using either SSH key or HTTPS token auth.

        Raises ``GitPushError`` on failure (the local commit survives).
        """
        self.ensure_initialised()
        push_url = _maybe_inject_token(url, token)
        env = self._auth_env(url, ssh_key_path=ssh_key_path, known_hosts_path=known_hosts_path)
        # Use a one-shot remote URL via -c remote.origin.url so we never write the
        # token into the repo's `.git/config`. Same idea for SSH so the agent can
        # rotate `ssh_key_path` without leaving stale config behind.
        with self._push_lock:
            try:
                subprocess.run(  # noqa: S603 - absolute git path, fixed arg list
                    [
                        self._git,
                        "-c", f"remote.{_REMOTE_NAME}.url={push_url}",
                        "push", "--", _REMOTE_NAME, f"HEAD:{branch}",
                    ],
                    cwd=self.root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise GitPushError(f"git push timed out after {timeout}s") from exc
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or "").strip()
                # Make sure no token ever appears in error text we hand back.
                if token:
                    stderr = stderr.replace(token, "[REDACTED]")
                raise GitPushError(f"git push failed ({exc.returncode}): {stderr}") from exc

    def write_and_commit(
        self,
        relative_path: str | Path,
        content: str,
        *,
        message: str,
    ) -> CommitResult | None:
        """Write ``content`` to ``relative_path`` and commit if it changed.

        Returns the commit info, or ``None`` when the file already matched on
        disk (no commit was made).

        Holds the commit lock for the whole stage→commit sequence so a
        concurrent device export can't interleave between ``git add`` and
        ``git commit`` (which would swallow this file into the other's commit
        or collide on ``.git/index.lock``).
        """
        with self._commit_lock:
            self.ensure_initialised()
            target = self.root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)

            # Avoid a commit when content is unchanged. Compare bytes to be precise.
            if target.exists() and target.read_text() == content:
                return None

            target.write_text(content)
            rel = target.relative_to(self.root)
            self._run(["add", str(rel)])

            # If `git add` produced no staged delta (e.g. content matched HEAD already), bail.
            if not self._has_staged_changes():
                return None

            # Numstat BEFORE commit so we can capture deltas against the index.
            added, removed = self._staged_numstat(rel)
            self._run(["commit", "-m", message])
            sha = self._run(["rev-parse", "HEAD"]).strip()
            return CommitResult(
                sha=sha,
                lines_added=added,
                lines_removed=removed,
                files_changed=1,
            )

    # --- Internals ---

    def _run(self, args: list[str]) -> str:
        env = os.environ.copy()
        # Belt-and-braces: don't let a global git config override per-repo identity.
        env.setdefault("GIT_AUTHOR_NAME", self._author_name)
        env.setdefault("GIT_AUTHOR_EMAIL", self._author_email)
        env.setdefault("GIT_COMMITTER_NAME", self._author_name)
        env.setdefault("GIT_COMMITTER_EMAIL", self._author_email)
        try:
            res = subprocess.run(  # noqa: S603 - resolved absolute path, fixed args list
                [self._git, *args],
                cwd=self.root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise GitError(f"git {args[0]} failed ({exc.returncode}): {stderr}") from exc
        return res.stdout

    def _has_staged_changes(self) -> bool:
        try:
            subprocess.run(  # noqa: S603 - resolved absolute path, fixed args list
                [self._git, "diff", "--cached", "--quiet"],
                cwd=self.root,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            # `diff --quiet` exits 1 when there ARE differences, which is what we want.
            return exc.returncode == 1
        return False

    def _auth_env(
        self,
        url: str,
        *,
        ssh_key_path: str | None,
        known_hosts_path: str | None,
    ) -> dict[str, str]:
        env = os.environ.copy()
        # Author identity (same as for commits, just belt-and-braces).
        env.setdefault("GIT_AUTHOR_NAME", self._author_name)
        env.setdefault("GIT_AUTHOR_EMAIL", self._author_email)
        # Don't let git prompt for credentials interactively from the daemon.
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env.setdefault("GIT_ASKPASS", "/bin/true")
        # SSH wrapper: pin the deploy key, accept-new the remote's host key.
        if ssh_key_path and _is_ssh_style(url):
            key = str(Path(ssh_key_path).expanduser())
            kh = known_hosts_path or str(Path(ssh_key_path).expanduser().parent / "known_hosts")
            env["GIT_SSH_COMMAND"] = (
                f"ssh -i {key} "
                f"-o IdentitiesOnly=yes "
                f"-o StrictHostKeyChecking=accept-new "
                f"-o UserKnownHostsFile={kh}"
            )
        return env

    def _staged_numstat(self, path: Path) -> tuple[int, int]:
        out = self._run(["diff", "--cached", "--numstat", "--", str(path)])
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    return int(parts[0]), int(parts[1])
                except ValueError:
                    continue
        return 0, 0
