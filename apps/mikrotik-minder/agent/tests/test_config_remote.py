"""git.remote config parsing."""

from __future__ import annotations

import pytest

from mikrotik_minder_agent.config import ConfigError, parse_config


def _wrap(remote: dict | None) -> dict:
    git = {"repo": "/var/lib/minder/configs"}
    if remote is not None:
        git["remote"] = remote
    return {
        "server": {"url": "https://x", "agent_token": "t"},
        "git": git,
        "devices": [
            {"name": "rtr", "address": "1.1.1.1", "username": "u", "password": "p"},
        ],
    }


def test_parse_remote_ssh() -> None:
    cfg = parse_config(_wrap({
        "url": "git@github.com:o/r.git",
        "ssh_key_path": "/home/minder/.ssh/deploy",
        "branch": "main",
    }))
    assert cfg.git is not None and cfg.git.remote is not None
    assert cfg.git.remote.url == "git@github.com:o/r.git"
    assert cfg.git.remote.ssh_key_path == "/home/minder/.ssh/deploy"
    assert cfg.git.remote.token is None
    assert cfg.git.remote.push is True


def test_parse_remote_https_with_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MTM_GIT_PAT", "ghp_secret")
    cfg = parse_config(_wrap({
        "url": "https://github.com/o/r.git",
        "token_env": "MTM_GIT_PAT",
    }))
    assert cfg.git.remote.token == "ghp_secret"


def test_remote_with_both_ssh_and_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MTM_GIT_PAT", "x")
    with pytest.raises(ConfigError, match="ssh_key_path or token"):
        parse_config(_wrap({
            "url": "https://github.com/o/r.git",
            "ssh_key_path": "/x",
            "token_env": "MTM_GIT_PAT",
        }))


def test_ssh_url_without_key_path_is_rejected() -> None:
    with pytest.raises(ConfigError, match="ssh_key_path"):
        parse_config(_wrap({"url": "git@github.com:o/r.git"}))


def test_remote_with_no_url_is_rejected() -> None:
    with pytest.raises(ConfigError, match="url"):
        parse_config(_wrap({"branch": "main"}))


def test_push_must_be_boolean() -> None:
    with pytest.raises(ConfigError, match="push"):
        parse_config(_wrap({
            "url": "https://x/r.git",
            "push": "no",  # string, not bool
        }))


def test_missing_remote_section_means_local_only() -> None:
    cfg = parse_config(_wrap(None))
    assert cfg.git.remote is None
