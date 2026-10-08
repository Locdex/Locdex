from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..models import MODEL_PROFILES
from ..sandbox import SandboxMode
from ..security import PermissionMode

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MODES = {"local_only", "balanced", "fast", "quality"}


class AgentSpecError(ValueError):
    pass


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    task: str
    model: str
    max_steps: int = 8
    mode: str = "balanced"
    permission_mode: str = PermissionMode.ASK.value
    sandbox_mode: str = SandboxMode.WORKSPACE_NETWORK.value
    write_scope: tuple[str, ...] = ()
    role: str = "worker"
    depends_on: tuple[str, ...] = ()
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "task": self.task,
            "model": self.model,
            "max_steps": self.max_steps,
            "mode": self.mode,
            "permission_mode": self.permission_mode,
            "sandbox_mode": self.sandbox_mode,
            "write_scope": list(self.write_scope),
            "depends_on": list(self.depends_on),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class AgentRunSpec:
    version: int
    agents: tuple[AgentDefinition, ...]
    defaults: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "defaults": dict(self.defaults),
            "agents": [agent.to_dict() for agent in self.agents],
        }


def _definition(raw: dict[str, Any], defaults: dict[str, Any]) -> AgentDefinition:
    if not isinstance(raw, dict):
        raise AgentSpecError("Each agents entry must be a mapping.")

    name = str(raw.get("name", "")).strip()
    if not _NAME_RE.match(name):
        raise AgentSpecError(
            "Agent name must be 1-64 characters using letters, numbers, '.', '_' or '-'."
        )

    task = str(raw.get("task", "")).strip()
    if not task:
        raise AgentSpecError(f"Agent {name!r} requires a non-empty task.")

    model = str(raw.get("model", defaults.get("model", ""))).strip().lower()
    if not model:
        raise AgentSpecError(
            f"Agent {name!r} requires a model or a defaults.model value."
        )
    if model not in MODEL_PROFILES:
        choices = ", ".join(sorted(MODEL_PROFILES))
        raise AgentSpecError(
            f"Agent {name!r} uses unknown model {model!r}. Choose one of: {choices}"
        )

    try:
        max_steps = int(raw.get("max_steps", defaults.get("max_steps", 8)))
    except (TypeError, ValueError) as exc:
        raise AgentSpecError(
            f"Agent {name!r} max_steps must be an integer."
        ) from exc
    if not 1 <= max_steps <= 20:
        raise AgentSpecError(
            f"Agent {name!r} max_steps must be between 1 and 20."
        )

    mode = str(
        raw.get("mode", defaults.get("mode", "balanced"))
    ).strip().lower()
    if mode not in _MODES:
        raise AgentSpecError(
            f"Agent {name!r} mode must be one of: {', '.join(sorted(_MODES))}"
        )

    permission_mode = str(
        raw.get(
            "permission_mode",
            defaults.get("permission_mode", PermissionMode.ASK.value),
        )
    ).strip().lower()
    permission_choices = {item.value for item in PermissionMode}
    if permission_mode not in permission_choices:
        raise AgentSpecError(
            f"Agent {name!r} permission_mode must be one of: "
            f"{', '.join(sorted(permission_choices))}"
        )

    sandbox_mode = str(
        raw.get(
            "sandbox_mode",
            defaults.get(
                "sandbox_mode",
                SandboxMode.WORKSPACE_NETWORK.value,
            ),
        )
    ).strip().lower()
    sandbox_choices = {item.value for item in SandboxMode}
    if sandbox_mode not in sandbox_choices:
        raise AgentSpecError(
            f"Agent {name!r} sandbox_mode must be one of: "
            f"{', '.join(sorted(sandbox_choices))}"
        )

    raw_scope = raw.get("write_scope", defaults.get("write_scope", []))
    if raw_scope is None:
        raw_scope = []
    if not isinstance(raw_scope, list) or not all(
        isinstance(item, str) and item.strip()
        for item in raw_scope
    ):
        raise AgentSpecError(
            f"Agent {name!r} write_scope must be a list of non-empty glob strings."
        )
    scope = tuple(
        item.replace("\\", "/").strip()
        for item in raw_scope
    )

    role = str(raw.get("role", defaults.get("role", "worker"))).strip()
    if not role or len(role) > 64:
        raise AgentSpecError(
            f"Agent {name!r} role must be a non-empty value up to 64 characters."
        )

    raw_dependencies = raw.get("depends_on", [])
    if raw_dependencies is None:
        raw_dependencies = []
    if not isinstance(raw_dependencies, list) or not all(
        isinstance(item, str) and _NAME_RE.match(item.strip())
        for item in raw_dependencies
    ):
        raise AgentSpecError(
            f"Agent {name!r} depends_on must be a list of agent names."
        )
    dependencies = tuple(dict.fromkeys(item.strip() for item in raw_dependencies))
    if name in dependencies:
        raise AgentSpecError(f"Agent {name!r} cannot depend on itself.")

    try:
        priority = int(raw.get("priority", defaults.get("priority", 0)))
    except (TypeError, ValueError) as exc:
        raise AgentSpecError(
            f"Agent {name!r} priority must be an integer."
        ) from exc
    if not -100 <= priority <= 100:
        raise AgentSpecError(
            f"Agent {name!r} priority must be between -100 and 100."
        )

    return AgentDefinition(
        name=name,
        task=task,
        model=model,
        max_steps=max_steps,
        mode=mode,
        permission_mode=permission_mode,
        sandbox_mode=sandbox_mode,
        write_scope=scope,
        role=role,
        depends_on=dependencies,
        priority=priority,
    )


def _validate_dependencies(agents: tuple[AgentDefinition, ...]) -> None:
    names = {agent.name for agent in agents}
    for agent in agents:
        missing = sorted(set(agent.depends_on) - names)
        if missing:
            raise AgentSpecError(
                f"Agent {agent.name!r} depends on unknown agents: {missing}"
            )

    dependencies = {
        agent.name: set(agent.depends_on)
        for agent in agents
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise AgentSpecError(
                f"Agent dependency cycle detected at {name!r}."
            )
        visiting.add(name)
        for dependency in dependencies[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in dependencies:
        visit(name)


def parse_agent_spec(data: dict[str, Any]) -> AgentRunSpec:
    if not isinstance(data, dict):
        raise AgentSpecError(
            "Agent config must contain a top-level mapping."
        )

    version = int(data.get("version", 1))
    if version != 1:
        raise AgentSpecError(
            f"Unsupported agent config version: {version}"
        )

    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise AgentSpecError("defaults must be a mapping.")

    raw_agents = data.get("agents")
    if not isinstance(raw_agents, list) or not raw_agents:
        raise AgentSpecError("agents must be a non-empty list.")
    if len(raw_agents) > 16:
        raise AgentSpecError(
            "A single multi-agent run supports at most 16 agents."
        )

    agents = tuple(
        _definition(raw, defaults)
        for raw in raw_agents
    )
    names = [agent.name for agent in agents]
    if len(names) != len(set(names)):
        raise AgentSpecError(
            "Agent names must be unique within a run."
        )

    _validate_dependencies(agents)
    return AgentRunSpec(
        version=version,
        agents=agents,
        defaults=dict(defaults),
    )


def load_agent_spec(path: str) -> AgentRunSpec:
    config = Path(path).expanduser().resolve()
    if not config.is_file():
        raise AgentSpecError(
            f"Agent config does not exist: {config}"
        )
    try:
        raw = yaml.safe_load(
            config.read_text(encoding="utf-8")
        )
    except (
        OSError,
        UnicodeDecodeError,
        yaml.YAMLError,
    ) as exc:
        raise AgentSpecError(
            f"Could not read agent config: {exc}"
        ) from exc
    return parse_agent_spec(raw)
