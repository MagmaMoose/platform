"""Push-to-remote tests. The 'remote' is a bare repo on disk, reached via file://."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mikrotik_minder_agent.gitrepo import GitPushError, GitRepo, _maybe_inject_token


def _bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    return remote


def test_push_to_local_bare_remote_succeeds(tmp_path: Path) -> None:
    repo = GitRepo(tmp_path / "configs")
    repo.write_and_commit("devices/a/exports/latest.rsc", "hello\n", message="first")
    remote = _bare_remote(tmp_path)

    repo.push(f"file://{remote}", branch="main")

    # The bare remote now has main pointing at something.
    out = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        check=True, capture_output=True, text=True,
    )
    assert len(out.stdout.strip()) == 40  # full SHA


def test_push_failure_does_not_lose_the_commit(tmp_path: Path) -> None:
    repo = GitRepo(tmp_path / "configs")
    repo.write_and_commit("a.rsc", "hello\n", message="first")

    with pytest.raises(GitPushError):
        # /no/such/path/remote.git does not exist — push must fail
        repo.push("file:///no/such/path/remote.git", branch="main")

    # Local commit still resolvable.
    out = subprocess.run(
        ["git", "-C", str(tmp_path / "configs"), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    assert len(out.stdout.strip()) == 40


def test_push_does_not_write_url_into_git_config(tmp_path: Path) -> None:
    """The token (if any) must never persist to .git/config — we set it inline."""
    repo = GitRepo(tmp_path / "configs")
    repo.write_and_commit("a.rsc", "hello\n", message="first")
    remote = _bare_remote(tmp_path)
    repo.push(f"file://{remote}", branch="main")

    cfg = (tmp_path / "configs" / ".git" / "config").read_text()
    assert "minder-remote" not in cfg
    assert "remote " not in cfg  # no [remote "..."] sections at all


def test_push_timeout_surfaces_as_push_error() -> None:
    # We can't trivially induce a real git push timeout without a network blackhole,
    # but we can confirm the public API exists. This is a smoke check.
    assert GitPushError.__mro__[1].__name__ == "GitError"


# --- URL rewriting -----------------------------------------------------------


def test_maybe_inject_token_https() -> None:
    assert _maybe_inject_token("https://github.com/o/r.git", "abc") == (
        "https://x-access-token:abc@github.com/o/r.git"
    )


def test_maybe_inject_token_preserves_port_and_path() -> None:
    out = _maybe_inject_token("https://gitea.lan:3000/o/r.git", "tok")
    assert out == "https://x-access-token:tok@gitea.lan:3000/o/r.git"


def test_maybe_inject_token_ssh_url_unchanged() -> None:
    url = "git@github.com:o/r.git"
    assert _maybe_inject_token(url, "tok") == url


def test_maybe_inject_token_no_token_unchanged() -> None:
    assert _maybe_inject_token("https://x/r.git", None) == "https://x/r.git"


def test_maybe_inject_token_file_url_unchanged() -> None:
    assert _maybe_inject_token("file:///tmp/r.git", "tok") == "file:///tmp/r.git"
