"""Per-agent offsite git remote delivered (sealed) by the control plane."""

from __future__ import annotations

from mikrotik_minder_agent.agentkeys import AgentKeyError
from mikrotik_minder_agent.config import GitRemoteConfig
from mikrotik_minder_agent.remoteconfig import build_git_remote, git_remote_changed


def test_build_git_remote_with_sealed_token() -> None:
    doc = {
        "git": {
            "remote": {
                "url": "https://github.com/platform1/dunmir-configs.git",
                "branch": "prod",
                "token_sealed": "BLOB",
            },
        },
    }
    r = build_git_remote(doc, unseal=lambda b: "ghp_secret" if b == "BLOB" else "")
    assert r is not None
    assert r.url == "https://github.com/platform1/dunmir-configs.git"
    assert r.branch == "prod"
    assert r.token == "ghp_secret"
    assert r.push is True


def test_url_only_defaults_branch_main_no_token() -> None:
    r = build_git_remote({"git": {"remote": {"url": "https://x/cfg.git"}}})
    assert r is not None
    assert r.branch == "main"
    assert r.token is None


def test_no_remote_returns_none() -> None:
    assert build_git_remote({}) is None
    assert build_git_remote({"git": {}}) is None
    assert build_git_remote({"git": {"remote": {}}}) is None
    assert build_git_remote({"git": {"remote": {"url": "  "}}}) is None


def test_sealed_token_without_vault_key_is_skipped() -> None:
    doc = {"git": {"remote": {"url": "https://x", "token_sealed": "BLOB"}}}
    assert build_git_remote(doc, unseal=None) is None


def test_sealed_token_decrypt_failure_is_skipped() -> None:
    def boom(_: str) -> str:
        raise AgentKeyError("wrong key")

    doc = {"git": {"remote": {"url": "https://x", "token_sealed": "BLOB"}}}
    assert build_git_remote(doc, unseal=boom) is None


def test_git_remote_changed_value_compare() -> None:
    a = GitRemoteConfig(url="https://x", token="t1")
    b = GitRemoteConfig(url="https://x", token="t1")
    c = GitRemoteConfig(url="https://x", token="t2")
    assert git_remote_changed(a, b) is False
    assert git_remote_changed(a, c) is True
    assert git_remote_changed(None, a) is True
    assert git_remote_changed(None, None) is False
