from __future__ import annotations

import json

import pytest

from locdex.extensions.mcp import MCPConfigError, load_mcp_servers
from locdex.session import SteeringQueue


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
