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
from ..verification import VerificationEngine
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
        self.verifier = VerificationEngine()

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
    def _preexisting_changed_paths(status_result: dict[str, Any]) -> set[str]:
        output = str(status_result.get("output", ""))
        paths: set[str] = set()
        for line in output.splitlines():
            if not line or line.startswith("##"):
                continue
            # git status --short: XY<space>path, with rename shown as old -> new.
            candidate = line[3:].strip() if len(line) >= 4 else ""
            if " -> " in candidate:
                candidate = candidate.split(" -> ", 1)[1].strip()
            if candidate:
                paths.add(candidate.replace("\\", "/"))
        return paths

    @staticmethod
    def _smoke_bootstrap_paths(
        task: str,
        bootstrap_result: dict[str, Any],
        *,
        limit: int = 4,
    ) -> list[str]:
        files = bootstrap_result.get("files")
        if not isinstance(files, list):
            return []

        task_lower = task.lower()
        task_terms = {
            token.strip(".,:;()[]{}'\"")
            for token in task_lower.split()
            if len(token.strip(".,:;()[]{}'\"")) >= 3
        }
        code_suffixes = (
            ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs",
            ".java", ".c", ".h", ".cpp", ".hpp",
        )

        def score(path: str) -> tuple[int, int, int, str]:
            lower = path.lower()
            points = 0
            if lower.endswith(code_suffixes):
                points += 3
            if any(term in lower for term in task_terms):
                points += 8
            if ("test" in lower or "spec" in lower) and any(
                word in task_lower for word in ("test", "fail", "bug", "fix")
            ):
                points += 5
            depth = lower.count("/")
            return (-points, depth, len(lower), lower)

        candidates = [
            str(path)
            for path in files
            if isinstance(path, str) and path.lower().endswith(code_suffixes)
        ]
        return sorted(candidates, key=score)[: max(1, min(int(limit), 6))]

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

        baseline_status = self._run_tool(
            repo_path=repo_path,
            task=task,
            name="git_status",
            args={},
            progress=progress,
        )
        tool_calls.append(
            {"tool": "git_status", "args": {}, "result": baseline_status}
        )
        if baseline_status.get("ok") is True:
            state.preexisting_changes = self._preexisting_changed_paths(baseline_status)
            if state.preexisting_changes:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "PRE-EXISTING USER CHANGES before this task: "
                            + ", ".join(sorted(state.preexisting_changes))
                            + ". Preserve unrelated existing work. Prefer exact replacements "
                            "over whole-file rewrites on dirty files."
                        ),
                    }
                )

        # The 1.5B smoke model is useful for validating mechanics but is weak at
        # planning multi-step tool use. Give it a small amount of exact source
        # deterministically so its first generation can focus on the edit.
        if self.model_key == "smoke":
            for path in self._smoke_bootstrap_paths(task, bootstrap_result):
                read_args = {"path": path, "start_line": 1, "end_line": 240}
                read_result = self._run_tool(
                    repo_path=repo_path,
                    task=task,
                    name="read_file",
                    args=read_args,
                    progress=progress,
                )
                read_call = {
                    "tool": "read_file",
                    "args": read_args,
                    "result": read_result,
                }
                tool_calls.append(read_call)
                if "error" not in read_result and read_result.get("path"):
                    state.files_read.add(str(read_result["path"]))
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"TOOL RESULT for read_file {path}:\n"
                            + self._compact_result(read_result, 4500)
                        ),
                    }
                )

        escalation_deferrals = 0
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
                    state.verification_attempts += 1
                    self._emit(progress, "[Agent] verify")
                    verification = self.verifier.verify(
                        repo_path,
                        sorted(state.files_modified),
                    )
                    state.verification = verification.to_dict()

                    if not verification.passed:
                        for failure in verification.failures:
                            detail = failure.output or f"{failure.name} failed"
                            state.failures.append(f"{failure.name}: {detail}")
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
                                    "Completion rejected because final verification failed. "
                                    "Use the failure evidence below to diagnose and repair the "
                                    "workspace, then verify again before finishing.\n"
                                    + self._compact_result(verification.to_dict(), 7000)
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
                    "verification": state.verification,
                    "verification_attempts": state.verification_attempts,
                    "preexisting_changes": sorted(state.preexisting_changes),
                    "tool_calls": tool_calls,
                }

            if action == "escalate":
                if (
                    requires_change
                    and last_mutation_index is None
                    and state.files_read
                    and escalation_deferrals < 2
                ):
                    escalation_deferrals += 1
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
                                "Escalation deferred: relevant workspace source has already "
                                "been provided, but no concrete edit has been attempted. "
                                "Use replace_in_file or write_file to make the smallest "
                                "reasonable change, then validate it. Escalate only if a "
                                "real tool attempt fails or the requested change is impossible."
                            ),
                        }
                    )
                    continue

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
                    "verification": state.verification,
                    "verification_attempts": state.verification_attempts,
                    "preexisting_changes": sorted(state.preexisting_changes),
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
