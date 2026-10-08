from __future__ import annotations

import json

import pytest

from locdex.extensions.mcp import MCPConfigError, load_mcp_servers
from locdex.session import PersistentSteeringQueue, SteeringQueue
from locdex.session import steering as steering_module


def test_mcp_config_loads_stdio_servers(tmp_path):
    locdex_dir = tmp_path / ".locdex"
    locdex_dir.mkdir()
    (locdex_dir / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "command": "python",
                        "args": ["server.py"],
                        "env": {"MODE": "read-only"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = load_mcp_servers(str(tmp_path))

    assert set(servers) == {"docs"}
    assert servers["docs"].command == "python"
    assert servers["docs"].args == ("server.py",)
    assert servers["docs"].env == {"MODE": "read-only"}


def test_invalid_mcp_config_is_rejected(tmp_path):
    locdex_dir = tmp_path / ".locdex"
    locdex_dir.mkdir()
    (locdex_dir / "mcp.json").write_text(
        '{"servers":{"broken":{"args":[]}}}',
        encoding="utf-8",
    )

    with pytest.raises(MCPConfigError, match="requires command"):
        load_mcp_servers(str(tmp_path))


def test_steering_queue_drains_and_cancels():
    queue = SteeringQueue()
    queue.submit("Do not touch migrations.")
    queue.submit("Use the existing parser.")

    assert queue.drain() == [
        "Do not touch migrations.",
        "Use the existing parser.",
    ]
    assert queue.drain() == []

    queue.cancel()
    assert queue.cancelled is True


def test_persistent_steering_queue_cross_process_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(
        steering_module,
        "user_cache_dir",
        lambda *args, **kwargs: str(tmp_path / "cache"),
    )

    first = PersistentSteeringQueue("session")
    second = PersistentSteeringQueue("session")

    first.submit("Do not touch auth.py.")
    assert second.drain() == ["Do not touch auth.py."]
    assert first.drain() == []

    second.cancel()
    assert first.cancelled is True
    first.reset_cancel()
    assert second.cancelled is False


def test_mcp_public_config_never_exposes_environment_values(tmp_path):
    locdex_dir = tmp_path / ".locdex"
    locdex_dir.mkdir()
    (locdex_dir / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "private": {
                        "command": "python",
                        "args": ["server.py"],
                        "env": {
                            "API_TOKEN": "super-secret-value",
                            "MODE": "read-only",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_mcp_servers(str(tmp_path))["private"]
    public = config.to_dict()

    assert public["env_keys"] == ["API_TOKEN", "MODE"]
    assert "env" not in public
    assert "super-secret-value" not in json.dumps(public)
