from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Callable

from ..agent import AgentEngine
from ..models import model_status
from ..runtime import RuntimeExecutionError
from ..security import PermissionController, PermissionMode
from .spec import AgentDefinition, AgentRunSpec
from .worktrees import (
    AgentWorkspace,
    WorktreeError,
    create_agent_worktree,
    ensure_clean_repository,
    new_run_id,
    repository_root,
)

ProgressCallback = Callable[[str], None]


class MultiAgentError(RuntimeError):
    pass


def _check_models(spec: AgentRunSpec) -> None:
    missing: list[str] = []
    for key in sorted({agent.model for agent in spec.agents}):
        status = model_status(key)
        if not status["installed"]:
            missing.append(key)
    if missing:
        commands = ", ".join(f"locdex model install {key}" for key in missing)
        raise MultiAgentError(
            "Install all agent models before starting a multi-agent run. "
            f"Missing: {missing}. Suggested commands: {commands}"
        )


def _agent_result(
    definition: AgentDefinition,
    workspace: AgentWorkspace,
    *,
    progress: ProgressCallback | None,
    approval_callback=None,
) -> dict[str, Any]:
    def emit(message: str) -> None:
        if progress is not None:
            progress(f"[Agent:{definition.name}] {message}")

    engine = AgentEngine(model_key=definition.model)
    permission_controller = PermissionController(
        definition.permission_mode,
        approval_callback=approval_callback
        if definition.permission_mode == PermissionMode.ASK.value
        else None,
    )
    try:
        result = engine.execute(
            definition.task,
            workspace.path,
            max_steps=definition.max_steps,
            routing_mode=definition.mode,
            write_scope=list(definition.write_scope),
            progress=emit,
            permission_controller=permission_controller,
            sandbox_mode=definition.sandbox_mode,
        )
    except RuntimeExecutionError as exc:
        result = {
            "status": "error",
            "model": definition.model,
            "summary": str(exc),
            "steps": 0,
        }
    except Exception as exc:  # noqa: BLE001
        result = {
            "status": "error",
            "model": definition.model,
            "summary": f"Agent execution failed: {exc}",
            "steps": 0,
        }

    return {
        "name": definition.name,
        "task": definition.task,
        "model": definition.model,
        "mode": definition.mode,
        "permission_mode": definition.permission_mode,
        "sandbox_mode": definition.sandbox_mode,
        "write_scope": list(definition.write_scope),
        "workspace": workspace.to_dict(),
        "result": result,
    }


def run_agents(
    spec: AgentRunSpec,
    repo_path: str = ".",
    *,
    parallel: int = 1,
    progress: ProgressCallback | None = None,
    approval_callback=None,
) -> dict[str, Any]:
    workers = max(1, min(int(parallel), 8, len(spec.agents)))
    ask_agents = [
        agent.name
        for agent in spec.agents
        if agent.permission_mode == PermissionMode.ASK.value
    ]
    if ask_agents and workers > 1:
        raise MultiAgentError(
            "Interactive ask permissions require --parallel 1. "
            f"Agents using ask mode: {ask_agents}"
        )
    if ask_agents and approval_callback is None:
        raise MultiAgentError(
            "Interactive ask permissions require an approval callback."
        )
    ensure_clean_repository(repo_path)
    _check_models(spec)

    root = repository_root(repo_path)
    run_id = new_run_id()
    workspaces: dict[str, AgentWorkspace] = {}

    for definition in spec.agents:
        workspaces[definition.name] = create_agent_worktree(
            str(root),
            agent_name=definition.name,
            run_id=run_id,
        )

    print_lock = Lock()

    def safe_progress(message: str) -> None:
        if progress is None:
            return
        with print_lock:
            progress(message)

    outcomes: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _agent_result,
                definition,
                workspaces[definition.name],
                progress=safe_progress,
                approval_callback=approval_callback,
            ): definition.name
            for definition in spec.agents
        }
        for future in as_completed(futures):
            name = futures[future]
            outcomes[name] = future.result()

    ordered = [outcomes[agent.name] for agent in spec.agents]
    completed = sum(
        1
        for row in ordered
        if row["result"].get("status") == "completed"
    )

    return {
        "run_id": run_id,
        "repo": str(root),
        "parallel": workers,
        "agents_total": len(ordered),
        "agents_completed": completed,
        "agents": ordered,
        "auto_commit": False,
        "auto_merge": False,
        "note": (
            "Each agent runs in an isolated Git worktree. Locdex does not "
            "auto-commit or auto-merge agent changes; review each workspace."
        ),
    }
