from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..context import ContextBudget, ContextCompiler
from ..models import get_model_profile, selected_model_key
from ..routing import (
    LearnedRouter,
    RoutingPolicy,
    RoutingSession,
    plan_execution,
    profile_task,
)
from ..routing.model_profile import from_local_profile
from ..runtime import LlamaCppSession, detect_hardware
from ..tools import TOOLS, ToolError, execute_tool
from .protocol import (
    AGENT_RESPONSE_SCHEMA,
    GIT_MUTATING_TOOLS,
    WORKSPACE_MUTATING_TOOLS,
    git_tool_allowed,
    system_prompt,
    task_requires_workspace_change,
)
from .state import AgentState

ProgressCallback = Callable[[str], None]

_VALIDATION_MARKERS = {
    "pytest",
    "unittest",
    "test",
    "tests",
    "ruff",
    "mypy",
    "pyright",
    "tsc",
    "vitest",
    "jest",
    "cargo",
    "go",
}


class AgentEngine:
    def __init__(self, model_key: str | None = None):
        self.model_key = model_key or selected_model_key()
        self.context = ContextCompiler()
        self.router = LearnedRouter()

    def prepare(
        self,
        task: str,
        repo_path: str,
        *,
        cloud_enabled: bool = False,
        routing_mode: str = "balanced",
    ) -> dict:
        state = AgentState(task, phase="retrieve")
        pack = self.context.compile(
            repo_path,
            task,
            ContextBudget(),
            cloud=cloud_enabled,
        )
        hardware = detect_hardware()
        profile = profile_task(
            task,
            repo_path,
            context_estimate=pack.total_tokens,
        )

        # Persisted/explicit local model selection is authoritative.
        selected = from_local_profile(get_model_profile(self.model_key))
        policy = RoutingPolicy(
            mode=routing_mode,
            allow_cloud=cloud_enabled,
        )
        decision = self.router.route(
            task=profile,
            models=[selected],
            policy=policy,
            session=RoutingSession(),
        )
        plan = plan_execution(
            local_model=decision.model,
            cloud_enabled=cloud_enabled,
            complexity="hard" if profile.reasoning_complexity >= 0.75 else "normal",
        )
        return {
            "state": state,
            "plan": plan,
            "context": pack,
            "task_profile": profile,
            "routing_decision": decision,
            "hardware": hardware,
            "selected_model": self.model_key,
        }

    @staticmethod
    def _emit(progress: ProgressCallback | None, message: str) -> None:
        if progress is not None:
            progress(message)

    @staticmethod
    def _repo_context(prepared: dict) -> str:
        chunks: list[str] = []
        for item in prepared["context"].items:
            chunks.append(f"[{item.label}]\n{item.content}")
        # The smoke profile has a 4K preferred context. Keep deterministic
        # metadata compact and let tools retrieve exact source on demand.
        return "\n\n".join(chunks)[:7000]

    @staticmethod
    def _compact_result(result: dict[str, Any], limit: int = 5000) -> str:
        text = json.dumps(result, ensure_ascii=False)
        if len(text) <= limit:
            return text
        return text[:limit] + "...<TRUNCATED>"

    @staticmethod
    def _is_validation_call(call: dict[str, Any]) -> bool:
        tool = call.get("tool")
        if tool == "run_tests":
            return True
        if tool != "run_command":
            return False
        args = call.get("args")
        if not isinstance(args, dict):
            return False
        argv = args.get("argv")
        if not isinstance(argv, list):
            return False
        normalized = {str(part).lower() for part in argv}
        return bool(normalized & _VALIDATION_MARKERS)

    @classmethod
    def _validation_after(
        cls,
        tool_calls: list[dict[str, Any]],
        mutation_index: int,
    ) -> tuple[bool, bool, bool]:
        attempted = False
        passed = False
        unavailable = False
        for call in tool_calls[mutation_index + 1 :]:
            if not cls._is_validation_call(call):
                continue
            attempted = True
            result = call.get("result")
            if not isinstance(result, dict):
                continue
            if result.get("ok") is True:
                passed = True
            if (
                result.get("returncode") is None
                and "No supported test runner" in str(result.get("output", ""))
            ):
                unavailable = True
        return attempted, passed, unavailable

    def _run_tool(
        self,
        *,
        repo_path: str,
        task: str,
        name: str,
        args: dict[str, Any],
        progress: ProgressCallback | None,
    ) -> dict[str, Any]:
        self._emit(progress, f"[Agent] {name}")
        explicit_intent = (
            git_tool_allowed(task, name)
            if name in GIT_MUTATING_TOOLS
            else False
        )
        try:
            return execute_tool(
                repo_path,
                name,
                args,
                explicit_user_intent=explicit_intent,
            )
        except ToolError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Tool execution failed: {exc}"}

    def execute(
        self,
        task: str,
        repo_path: str = ".",
        *,
        max_steps: int = 6,
        routing_mode: str = "balanced",
        session: Any | None = None,
        progress: ProgressCallback | None = None,
    ) -> dict:
        prepared = self.prepare(
            task,
            repo_path,
            cloud_enabled=False,
            routing_mode=routing_mode,
        )
        state: AgentState = prepared["state"]
        state.phase = "act"

        self._emit(
            progress,
            f"[Agent] Loading {self.model_key} once for this task...",
        )
        local_session = session or LlamaCppSession(
            model_key=self.model_key,
            hardware=prepared["hardware"],
        )

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": system_prompt(
                    self._repo_context(prepared),
                    self.model_key,
                ),
            },
            {"role": "user", "content": task},
        ]
        tool_calls: list[dict[str, Any]] = []
        requires_change = task_requires_workspace_change(task)
        last_mutation_index: int | None = None

        # Deterministic bootstrap: show the model the concrete file set before
        # spending a generation deciding whether to list the repository.
        bootstrap_args = {"path": ".", "limit": 120}
        bootstrap_result = self._run_tool(
            repo_path=repo_path,
            task=task,
            name="list_files",
            args=bootstrap_args,
            progress=progress,
        )
        bootstrap_call = {
            "tool": "list_files",
            "args": bootstrap_args,
            "result": bootstrap_result,
        }
        tool_calls.append(bootstrap_call)
        messages.append(
            {
                "role": "user",
                "content": (
                    "TOOL RESULT for list_files:\n"
                    + self._compact_result(bootstrap_result, 3500)
                ),
            }
        )

        step_cap = max(1, min(int(max_steps), 20))
        for step in range(1, step_cap + 1):
            state.attempts = step
            self._emit(
                progress,
                f"[Agent] Step {step}/{step_cap}: choosing next action...",
            )
            decision = local_session.json_completion(
                messages,
                AGENT_RESPONSE_SCHEMA,
                max_tokens=512,
                temperature=0.0,
            )
            action = str(decision.get("action", ""))

            if action == "final":
                if requires_change and last_mutation_index is None:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": json.dumps(decision, ensure_ascii=False),
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Completion rejected: this task requires a workspace "
                                "change, but no successful write/edit/delete tool has run. "
                                "Inspect the relevant file and make the concrete change."
                            ),
                        }
                    )
                    continue

                if last_mutation_index is not None:
                    attempted, passed, unavailable = self._validation_after(
                        tool_calls,
                        last_mutation_index,
                    )
                    if not attempted:
                        verify_args: dict[str, Any] = {}
                        verify_result = self._run_tool(
                            repo_path=repo_path,
                            task=task,
                            name="run_tests",
                            args=verify_args,
                            progress=progress,
                        )
                        verify_call = {
                            "tool": "run_tests",
                            "args": verify_args,
                            "result": verify_result,
                        }
                        tool_calls.append(verify_call)
                        attempted, passed, unavailable = self._validation_after(
                            tool_calls,
                            last_mutation_index,
                        )
                        if attempted and not (passed or unavailable):
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": json.dumps(
                                        decision,
                                        ensure_ascii=False,
                                    ),
                                }
                            )
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "Automatic validation failed after your edit. "
                                        "Diagnose the failure and continue.\n"
                                        + self._compact_result(verify_result)
                                    ),
                                }
                            )
                            continue

                    diff_result = self._run_tool(
                        repo_path=repo_path,
                        task=task,
                        name="git_diff",
                        args={},
                        progress=progress,
                    )
                    if diff_result.get("ok") is True:
                        state.current_diff = str(diff_result.get("output", ""))

                state.phase = "done"
                return {
                    "status": "completed",
                    "model": self.model_key,
                    "summary": str(
                        decision.get("summary")
                        or "Task completed."
                    ),
                    "confidence": float(decision.get("confidence", 0.8)),
                    "steps": step,
                    "files_read": sorted(state.files_read),
                    "files_modified": sorted(state.files_modified),
                    "diff": state.current_diff,
                    "tool_calls": tool_calls,
                }

            if action == "escalate":
                state.phase = "escalate"
                return {
                    "status": "escalate",
                    "model": self.model_key,
                    "summary": str(
                        decision.get("reason")
                        or decision.get("summary")
                        or "Local model requested escalation."
                    ),
                    "confidence": float(decision.get("confidence", 0.0)),
                    "steps": step,
                    "files_read": sorted(state.files_read),
                    "files_modified": sorted(state.files_modified),
                    "tool_calls": tool_calls,
                }

            if action != "tool":
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Protocol error: action must be tool, final, or escalate."
                        ),
                    }
                )
                continue

            tool_name = str(decision.get("tool", ""))
            raw_args = decision.get("args")
            tool_args = raw_args if isinstance(raw_args, dict) else {}
            if tool_name not in TOOLS:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Protocol error: unknown tool {tool_name!r}.",
                    }
                )
                continue

            result = self._run_tool(
                repo_path=repo_path,
                task=task,
                name=tool_name,
                args=tool_args,
                progress=progress,
            )
            call = {
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            }
            tool_calls.append(call)

            if "error" not in result:
                if tool_name == "read_file" and result.get("path"):
                    state.files_read.add(str(result["path"]))
                if (
                    tool_name in WORKSPACE_MUTATING_TOOLS
                    and result.get("ok") is True
                ):
                    path = result.get("path")
                    if path:
                        state.files_modified.add(str(path))
                    last_mutation_index = len(tool_calls) - 1

            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(decision, ensure_ascii=False),
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"TOOL RESULT for {tool_name}:\n"
                        + self._compact_result(result)
                    ),
                }
            )

        state.phase = "incomplete"
        return {
            "status": "incomplete",
            "model": self.model_key,
            "summary": (
                f"Agent reached the bounded step limit ({step_cap}) before "
                "producing evidence-backed completion."
            ),
            "confidence": 0.0,
            "steps": step_cap,
            "files_read": sorted(state.files_read),
            "files_modified": sorted(state.files_modified),
            "tool_calls": tool_calls,
        }
