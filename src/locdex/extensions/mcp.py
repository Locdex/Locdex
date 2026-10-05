from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..sandbox import SandboxMode, sandbox_environment, wrap_command


class MCPUnavailableError(RuntimeError):
    pass


class MCPConfigError(ValueError):
    pass


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env or {}),
        }


def load_mcp_servers(repo_path: str) -> dict[str, MCPServerConfig]:
    root = Path(repo_path).resolve()
    path = root / ".locdex" / "mcp.json"
    if not path.is_file():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MCPConfigError(f"Could not read .locdex/mcp.json: {exc}") from exc

    raw_servers = data.get("servers")
    if not isinstance(raw_servers, dict):
        raise MCPConfigError(".locdex/mcp.json must contain an object named 'servers'.")

    result: dict[str, MCPServerConfig] = {}
    for name, raw in raw_servers.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(raw, dict):
            raise MCPConfigError("Each MCP server requires a non-empty name and object config.")
        command = str(raw.get("command", "")).strip()
        if not command:
            raise MCPConfigError(f"MCP server {name!r} requires command.")
        args = raw.get("args", [])
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            raise MCPConfigError(f"MCP server {name!r} args must be a list of strings.")
        env = raw.get("env", {})
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in env.items()
        ):
            raise MCPConfigError(f"MCP server {name!r} env must be a string mapping.")
        result[name] = MCPServerConfig(
            name=name,
            command=command,
            args=tuple(args),
            env=dict(env),
        )
    return result


def _import_sdk():
    try:
        from mcp import Client, StdioServerParameters
    except ImportError as exc:
        raise MCPUnavailableError(
            "MCP support is optional. Install it with: pip install 'locdex[mcp]'"
        ) from exc
    return Client, StdioServerParameters


def _server_process(
    repo_path: str,
    config: MCPServerConfig,
    sandbox_mode: str,
) -> tuple[str, list[str], dict[str, str]]:
    command = [config.command, *config.args]
    wrapped, _ = wrap_command(
        repo_path,
        str(Path(repo_path).resolve()),
        command,
        sandbox_mode,
    )

    env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            marker in key.upper()
            for marker in (
                "TOKEN",
                "SECRET",
                "PASSWORD",
                "API_KEY",
                "PRIVATE_KEY",
                "CREDENTIAL",
            )
        )
    }
    env.update(sandbox_environment(sandbox_mode))
    env.update(config.env or {})

    return wrapped[0], wrapped[1:], env


def _tool_payload(tool: Any) -> dict[str, Any]:
    return {
        "name": str(tool.name),
        "title": getattr(tool, "title", None),
        "description": getattr(tool, "description", None),
        "input_schema": getattr(tool, "input_schema", None),
    }


async def _list_tools_async(
    repo_path: str,
    config: MCPServerConfig,
    sandbox_mode: str,
) -> dict[str, Any]:
    Client, StdioServerParameters = _import_sdk()
    command, args, env = _server_process(repo_path, config, sandbox_mode)
    server = StdioServerParameters(command=command, args=args, env=env)
    async with Client(server) as client:
        result = await client.list_tools()
        return {
            "server": config.name,
            "protocol_version": getattr(client, "protocol_version", None),
            "tools": [_tool_payload(tool) for tool in result.tools],
        }


async def _call_tool_async(
    repo_path: str,
    config: MCPServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
    sandbox_mode: str,
) -> dict[str, Any]:
    Client, StdioServerParameters = _import_sdk()
    command, args, env = _server_process(repo_path, config, sandbox_mode)
    server = StdioServerParameters(command=command, args=args, env=env)
    async with Client(server) as client:
        result = await client.call_tool(tool_name, arguments)
        blocks: list[Any] = []
        for block in result.content:
            if hasattr(block, "model_dump"):
                blocks.append(block.model_dump())
            else:
                blocks.append(str(block))
        return {
            "server": config.name,
            "tool": tool_name,
            "is_error": bool(getattr(result, "is_error", False)),
            "content": blocks,
            "structured_content": getattr(result, "structured_content", None),
        }


def list_mcp_tools(
    repo_path: str,
    server_name: str,
    *,
    sandbox_mode: str = SandboxMode.WORKSPACE_NETWORK.value,
) -> dict[str, Any]:
    servers = load_mcp_servers(repo_path)
    try:
        config = servers[server_name]
    except KeyError as exc:
        raise MCPConfigError(f"Unknown MCP server: {server_name}") from exc
    return asyncio.run(_list_tools_async(repo_path, config, sandbox_mode))


def call_mcp_tool(
    repo_path: str,
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    sandbox_mode: str = SandboxMode.WORKSPACE_NETWORK.value,
) -> dict[str, Any]:
    servers = load_mcp_servers(repo_path)
    try:
        config = servers[server_name]
    except KeyError as exc:
        raise MCPConfigError(f"Unknown MCP server: {server_name}") from exc
    return asyncio.run(
        _call_tool_async(
            repo_path,
            config,
            tool_name,
            arguments or {},
            sandbox_mode,
        )
    )
