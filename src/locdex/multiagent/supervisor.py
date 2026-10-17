from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Callable

from ..agent import AgentEngine
from ..models import model_status
from ..routing.execution import execute_with_escalation
from ..runtime import RuntimeExecutionError
from ..security import PermissionController, PermissionMode
from .spec import AgentDefinition, AgentRunSpec
from .worktrees import (
    AgentWorkspace,
    WorktreeError,
    create_agent_worktree,
    ensure_clean_repository,
    inherit_workspace_changes,
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
        commands = ", ".join(
            f"locdex model install {key}"
            for key in missing
        )
        raise MultiAgentError(
            "Install all agent models before starting a multi-agent run. "
            f"Missing: {missing}. Suggested commands: {commands}"
        )


def _dependency_context(
    definition: AgentDefinition,
    outcomes: dict[str, dict[str, Any]],
) -> str:
    if not definition.depends_on:
        return ""
    rows = [
        "UPSTREAM AGENT HANDOFF",
        "The dependency workspaces have been inherited into this worktree. "
        "Re-read exact source before editing.",
    ]
    for name in definition.depends_on:
        outcome = outcomes[name]
        result = outcome["result"]
        rows.append(
            f"- {name}: status={result.get('status')} | "
            f"summary={str(result.get('summary', ''))[:700]} | "
            f"changed={outcome.get('changed_files', [])[:20]}"
        )
    return "\n".join(rows)[:5000]


def _agent_result(
    definition: AgentDefinition,
    workspace: AgentWorkspace,
    *,
    progress: ProgressCallback | None,
    approval_callback=None,
    additional_context: str | None = None,
) -> dict[str, Any]:
    def emit(message: str) -> None:
        if progress is not None:
            progress(f"[Agent:{definition.name}] {message}")

    engine = AgentEngine(model_key=definition.model)
    permission_controller = PermissionController(
        definition.permission_mode,
        approval_callback=(
            approval_callback
            if definition.permission_mode == PermissionMode.ASK.value
            else None
        ),
    )
    try:
        result = execute_with_escalation(
            engine,
            definition.task,
            workspace.path,
            max_steps=definition.max_steps,
            routing_mode=definition.mode,
            write_scope=list(definition.write_scope),
            progress=emit,
            permission_controller=permission_controller,
            sandbox_mode=definition.sandbox_mode,
            additional_context=additional_context,
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

    changed = sorted(
        {
            str(path).replace("\\", "/")
            for path in (result.get("files_modified") or [])
            if str(path).strip()
        }
    )
    return {
        "name": definition.name,
        "role": definition.role,
        "task": definition.task,
        "model": definition.model,
        "mode": definition.mode,
        "permission_mode": definition.permission_mode,
        "sandbox_mode": definition.sandbox_mode,
        "write_scope": list(definition.write_scope),
        "depends_on": list(definition.depends_on),
        "priority": definition.priority,
        "workspace": workspace.to_dict(),
        "changed_files": changed,
        "result": result,
    }


def _blocked_result(
    definition: AgentDefinition,
    workspace: AgentWorkspace,
    reason: str,
) -> dict[str, Any]:
    return {
        "name": definition.name,
        "role": definition.role,
        "task": definition.task,
        "model": definition.model,
        "mode": definition.mode,
        "permission_mode": definition.permission_mode,
        "sandbox_mode": definition.sandbox_mode,
        "write_scope": list(definition.write_scope),
        "depends_on": list(definition.depends_on),
        "priority": definition.priority,
        "workspace": workspace.to_dict(),
        "changed_files": [],
        "result": {
            "status": "blocked",
            "model": definition.model,
            "summary": reason,
            "steps": 0,
        },
    }


def _integration_conflicts(
    ordered: list[dict[str, Any]],
    definitions: dict[str, AgentDefinition],
) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for row in ordered:
        if row["result"].get("status") != "completed":
            continue
        for path in row.get("changed_files", []):
            owners.setdefault(path, []).append(row["name"])
    return {
        path: names
        for path, names in owners.items()
        if any(
            not _depends_transitively(left, right, definitions)
            and not _depends_transitively(right, left, definitions)
            for i, left in enumerate(names)
            for right in names[i + 1:]
        )
    }


def _worker_limit(spec: AgentRunSpec, parallel: int) -> int:
    try:
        requested = int(parallel)
    except (TypeError, ValueError) as exc:
        raise MultiAgentError("Parallel worker count must be a positive integer.") from exc
    if requested < 1 or requested > 8:
        raise MultiAgentError("--parallel must be between 1 and 8.")
    return min(requested, len(spec.agents))


def plan_agents(spec: AgentRunSpec, *, parallel: int = 1) -> dict[str, Any]:
    """Build the same dependency-aware execution waves without loading models.

    Safe for low-memory systems: no GGUF, subprocess, Git worktree, network,
    repository write or permission prompt is required to validate scheduling.
    """
    workers = _worker_limit(spec, parallel)
    by_name = {agent.name: agent for agent in spec.agents}
    index = {agent.name: i for i, agent in enumerate(spec.agents)}
    pending = set(by_name)
    finished: set[str] = set()
    waves: list[dict[str, Any]] = []

    while pending:
        ready = [
            by_name[name] for name in pending
            if set(by_name[name].depends_on) <= finished
        ]
        if not ready:
            raise MultiAgentError("Agent dependencies contain a cycle or unknown dependency.")
        ready.sort(key=lambda a: (-a.priority, index[a.name]))
        batch = ready[:workers]
        waves.append({
            "wave": len(waves) + 1,
            "agents": [{
                "name": a.name,
                "role": a.role,
                "model": a.model,
                "task": a.task,
                "depends_on": list(a.depends_on),
                "write_scope": list(a.write_scope),
                "priority": a.priority,
            } for a in batch],
        })
        names = {a.name for a in batch}
        finished.update(names)
        pending -= names

    return {
        "schema": "locdex-agents-plan-v1",
        "dry_run": True,
        "agents_total": len(spec.agents),
        "parallel": workers,
        "waves": waves,
        "requires_models": sorted({agent.model for agent in spec.agents}),
        "model_loading": False,
        "worktrees_created": False,
        "notes": [
            "This plan validates orchestration order only; it does not measure model coding accuracy.",
            "Parallel local agents can load separate GGUF models; use --parallel 1 on memory-constrained systems.",
        ],
    }


def _depends_transitively(
    descendant: str, ancestor: str, definitions: dict[str, AgentDefinition],
) -> bool:
    """Return whether descendant extends work from ancestor."""
    visited: set[str] = set()
    stack = list(definitions[descendant].depends_on)
    while stack:
        node = stack.pop()
        if node == ancestor:
            return True
        if node not in visited:
            visited.add(node)
            stack.extend(definitions[node].depends_on)
    return False



def run_agents(
    spec: AgentRunSpec,
    repo_path: str = ".",
    *,
    parallel: int = 1,
    progress: ProgressCallback | None = None,
    approval_callback=None,
) -> dict[str, Any]:
    workers = _worker_limit(spec, parallel)
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
    definitions = {
        agent.name: agent
        for agent in spec.agents
    }
    order_index = {
        agent.name: index
        for index, agent in enumerate(spec.agents)
    }
    workspaces: dict[str, AgentWorkspace] = {
        definition.name: create_agent_worktree(
            str(root),
            agent_name=definition.name,
            run_id=run_id,
        )
        for definition in spec.agents
    }

    print_lock = Lock()

    def safe_progress(message: str) -> None:
        if progress is None:
            return
        with print_lock:
            progress(message)

    outcomes: dict[str, dict[str, Any]] = {}
    pending = set(definitions)

    while pending:
        blocked_now: list[str] = []
        for name in sorted(pending):
            definition = definitions[name]
            failed = [
                dependency
                for dependency in definition.depends_on
                if dependency in outcomes
                and outcomes[dependency]["result"].get("status") != "completed"
            ]
            if failed:
                outcomes[name] = _blocked_result(
                    definition,
                    workspaces[name],
                    "Blocked because dependency agents did not complete: "
                    + ", ".join(failed),
                )
                blocked_now.append(name)
        pending.difference_update(blocked_now)
        if not pending:
            break

        ready = [
            definitions[name]
            for name in pending
            if all(
                dependency in outcomes
                and outcomes[dependency]["result"].get("status") == "completed"
                for dependency in definitions[name].depends_on
            )
        ]
        if not ready:
            raise MultiAgentError(
                "No runnable agents remain. Check dependency configuration."
            )

        ready.sort(
            key=lambda item: (
                -item.priority,
                order_index[item.name],
            )
        )
        batch = ready[:workers]
        runnable: list[tuple[AgentDefinition, str]] = []

        for definition in batch:
            dependency_workspaces = [
                workspaces[name]
                for name in definition.depends_on
            ]
            inherited = inherit_workspace_changes(
                workspaces[definition.name],
                dependency_workspaces,
            )
            if not inherited["ok"]:
                conflicts = inherited["conflicts"]
                outcomes[definition.name] = _blocked_result(
                    definition,
                    workspaces[definition.name],
                    "Blocked because dependency changes conflict before execution: "
                    + str(conflicts),
                )
                pending.discard(definition.name)
                continue
            runnable.append(
                (
                    definition,
                    _dependency_context(definition, outcomes),
                )
            )

        if not runnable:
            continue

        safe_progress(
            "[Supervisor] Starting " + ", ".join(
                d.name for d, _ in runnable
            ) + f" (parallel={len(runnable)})."
        )
        with ThreadPoolExecutor(
            max_workers=min(workers, len(runnable))
        ) as pool:
            futures = {
                pool.submit(
                    _agent_result,
                    definition,
                    workspaces[definition.name],
                    progress=safe_progress,
                    approval_callback=approval_callback,
                    additional_context=context,
                ): definition.name
                for definition, context in runnable
            }
            for future in as_completed(futures):
                name = futures[future]
                outcomes[name] = future.result()
                pending.discard(name)
                safe_progress(
                    f"[Supervisor] {name}: "
                    f"{outcomes[name]['result'].get('status', 'unknown')}"
                )

    ordered = [
        outcomes[agent.name]
        for agent in spec.agents
    ]
    completed = sum(
        1
        for row in ordered
        if row["result"].get("status") == "completed"
    )
    conflicts = _integration_conflicts(ordered, definitions)
    integration_plan = [
        {
            "agent": row["name"],
            "branch": row["workspace"]["branch"],
            "workspace": row["workspace"]["path"],
            "depends_on": row["depends_on"],
            "changed_files": row.get("changed_files", []),
            "conflicting_files": [
                path
                for path, names in conflicts.items()
                if row["name"] in names
            ],
        }
        for row in ordered
        if row["result"].get("status") == "completed"
    ]

    return {
        "run_id": run_id,
        "repo": str(root),
        "parallel": workers,
        "agents_total": len(ordered),
        "agents_completed": completed,
        "agents": ordered,
        "integration_conflicts": conflicts,
        "integration_plan": integration_plan,
        "auto_commit": False,
        "auto_merge": False,
        "note": (
            "Agents run in isolated Git worktrees. Dependency changes are "
            "copied into downstream worktrees without committing. Locdex does "
            "not auto-commit or auto-merge final changes; review the integration "
            "plan and resolve any reported file conflicts."
        ),
    }
