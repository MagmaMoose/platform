from __future__ import annotations

import threading
from pathlib import Path

import pytest

from mikrotik_minder_agent.gitrepo import GitRepo


def test_first_write_creates_repo_and_commits(tmp_path: Path) -> None:
    repo = GitRepo(tmp_path / "configs")
    result = repo.write_and_commit("devices/a/exports/latest.rsc", "hello\n", message="first")
    assert result is not None
    assert result.lines_added == 1
    assert result.lines_removed == 0
    assert len(result.sha) >= 7
    assert (tmp_path / "configs" / "devices/a/exports/latest.rsc").read_text() == "hello\n"
    assert (tmp_path / "configs" / ".git").is_dir()


def test_unchanged_content_does_not_commit(tmp_path: Path) -> None:
    repo = GitRepo(tmp_path / "configs")
    repo.write_and_commit("devices/a/exports/latest.rsc", "hello\n", message="first")
    second = repo.write_and_commit("devices/a/exports/latest.rsc", "hello\n", message="second")
    assert second is None  # no commit; content matched


def test_changed_content_reports_line_delta(tmp_path: Path) -> None:
    repo = GitRepo(tmp_path / "configs")
    path = "devices/a/exports/latest.rsc"
    repo.write_and_commit(path, "a\nb\nc\n", message="first")
    updated = repo.write_and_commit(path, "a\nB\nc\nd\n", message="second")
    assert updated is not None
    # Modified line counts as 1 add + 1 remove; new line counts as 1 add.
    assert updated.lines_added == 2
    assert updated.lines_removed == 1


def test_each_device_lives_in_its_own_directory(tmp_path: Path) -> None:
    repo = GitRepo(tmp_path / "configs")
    repo.write_and_commit("devices/core/exports/latest.rsc", "core-config\n", message="core")
    repo.write_and_commit("devices/edge/exports/latest.rsc", "edge-config\n", message="edge")
    assert (tmp_path / "configs/devices/core/exports/latest.rsc").exists()
    assert (tmp_path / "configs/devices/edge/exports/latest.rsc").exists()


def test_git_binary_missing_is_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import shutil as _shutil

    monkeypatch.setattr(_shutil, "which", lambda _name: None)
    with pytest.raises(Exception, match="git"):
        GitRepo(tmp_path / "x")


def test_concurrent_commits_are_serialised(tmp_path: Path) -> None:
    """The daemon shares one GitRepo across one-thread-per-device exports.

    Without an internal lock, concurrent ``git add``/``commit`` race on
    ``.git/index.lock`` and a commit can swallow another device's staged file.
    With the lock, every device gets its own clean, single-file commit.
    """
    repo = GitRepo(tmp_path / "configs")
    repo.ensure_initialised()

    n = 12
    start = threading.Barrier(n)
    results: dict[int, object] = {}
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            start.wait()  # release all threads together to maximise contention
            results[i] = repo.write_and_commit(
                f"devices/dev{i:02d}/exports/latest.rsc",
                f"config for device {i}\n",
                message=f"dev{i:02d}: export",
            )
        except Exception as exc:  # record so the assertion can report the failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent commits raised: {errors}"
    # One commit per device, and the history has exactly n commits (none swallowed).
    assert len(results) == n
    assert all(r is not None for r in results.values())
    commit_count = int(repo._run(["rev-list", "--count", "HEAD"]).strip())
    assert commit_count == n
    # Every device's file landed intact and nothing is left staged/uncommitted.
    for i in range(n):
        path = tmp_path / "configs" / f"devices/dev{i:02d}/exports/latest.rsc"
        assert path.read_text() == f"config for device {i}\n"
    assert repo._run(["status", "--porcelain"]).strip() == ""
