"""Regression: `check` is local-only so it must not require the agent bearer."""

from __future__ import annotations

import pytest

from mikrotik_minder_agent.config import ConfigError, parse_config


def _doc() -> dict:
    return {
        "server": {"url": "https://x", "agent_token_env": "MTM_TOKEN_NOT_SET"},
        "devices": [
            {"name": "a", "address": "10.0.0.1", "username": "u", "password": "p"},
        ],
    }


def test_check_path_tolerates_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MTM_TOKEN_NOT_SET", raising=False)
    cfg = parse_config(_doc(), require_server_token=False)
    assert cfg.server.agent_token == ""  # placeholder; check never calls the worker


def test_run_path_still_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MTM_TOKEN_NOT_SET", raising=False)
    with pytest.raises(ConfigError, match="MTM_TOKEN_NOT_SET"):
        parse_config(_doc())
