from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from ..context_manager import ContextManagerConfig, maybe_compact
from ..intelligence import (
    find_references,
    find_symbol,
    get_reference_context,
    get_symbol_source,
    plan_retrieval,
    related_files,
)
from ..models import get_model_profile
from ..runtime import LlamaCppSession, detect_hardware
from ..sandbox import SandboxMode, SandboxPolicy
from ..security import PermissionController
from ..tools import TOOLS
from ..task_state import TaskState
from .change_journal import ChangeJournal
from .engine import AgentEngine as BaseAgentEngine
from .guards import (
    clean_model_result,
    guard_mutation_result,
    is_test_path,
    preexisting_changed_paths,
    snapshot_file,
    task_explicitly_allows_test_changes,
    task_explicitly_names_change,
)
from .protocol import WORKSPACE_MUTATING_TOOLS


class _RepairAwareSession:
    def __init__(self, inner: Any, engine: AgentEngine):
        self.inner = inner
        self.engine = engine
        self._signature_counts: dict[str, int] = {}

    def json_completion(self, messages, schema, **kwargs):
        task_state = getattr(self.engine, "task_state", None)
        if task_state is None:
            task_state = TaskState.from_task("")
            self.engine.task_state = task_state

        context_config = getattr(self.engine, "context_manager_config", None)
        if context_config is None:
            context_config = ContextManagerConfig()
            self.engine.context_manager_config = context_config

        compacted = maybe_compact(
            list(messages),
            task_state,
            context_config,
        )
        self.engine._last_context_compaction = compacted
        messages = compacted.messages

        if (
            self.engine._repair_required
            and self.engine._mutations_since_validation >= 2
        ):
            return {
                "action": "tool",
                "tool": "run_tests",
                "args": {},
                "summary": "Re-run validation after bounded repair edits.",
                "confidence": 1.0,
            }

        if messages:
            latest = str(messages[-1].get("content", "")).lower()
            if "final verification failed" in latest:
                self.engine._repair_required = True

        decision = self.inner.json_completion(messages, schema, **kwargs)

        for guard_round in range(3):
            args = (
                decision.get("args")
                if isinstance(decision.get("args"), dict)
                else {}
            )
            action = str(decision.get("action", ""))
            tool = str(decision.get("tool", ""))
            path = args.get("path")

            preloaded_paths = set(getattr(self.engine, "_preloaded_paths", set()))
            unchanged_preloaded_read = (
                action == "tool"
                and tool == "read_file"
                and isinstance(path, str)
                and path in preloaded_paths
                and path not in set(self.engine.task_state.modified_files)
            )

            signature = json.dumps(
                {
                    "action": decision.get("action"),
                    "tool": decision.get("tool"),
                    "args": args,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            self._signature_counts[signature] = (
                self._signature_counts.get(signature, 0) + 1
            )
            repeated = (
                action == "tool"
                and self._signature_counts[signature] >= 2
            )

            if not unchanged_preloaded_read and not repeated:
                break

            if guard_round >= 2:
                return {
                    "action": "escalate",
                    "reason": (
                        "Local model could not make progress after fresh deterministic "
                        "retrieval and bounded edit re-planning."
                    ),
                    "confidence": 0.1,
                }

            retry_messages = list(messages)
            retry_messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(decision, ensure_ascii=False),
                }
            )

            if unchanged_preloaded_read:
                instruction = (
                    f"{path} was retrieved immediately before this decision and has not "
                    "changed. Do not read it again. Make the smallest concrete mutation "
                    "or validate. For Python functions/classes prefer replace_symbol for "
                    "an existing symbol and insert_after_symbol for a missing sibling."
                )
            else:
                instruction = (
                    "The exact same tool call has already failed to make progress. "
                    "Do not repeat it and do not reread unchanged source. Switch to a "
                    "materially different edit. For Python functions/classes prefer "
                    "replace_symbol or insert_after_symbol, then validate."
                )

            retry_messages.append(
                {
                    "role": "user",
                    "content": instruction,
                }
            )
            decision = self.inner.json_completion(
                retry_messages,
                schema,
                **kwargs,
            )

        args = (
            decision.get("args")
            if isinstance(decision.get("args"), dict)
            else {}
        )
        action = str(decision.get("action", ""))
        tool = str(decision.get("tool", ""))
        path = args.get("path")
        if action == "tool":
            detail = f"tool:{tool}"
            if isinstance(path, str) and path:
                detail += f" path={path}"
            self.engine.task_state.add_decision(detail)
            self.engine.task_state.set_next_action(detail)
        elif action == "final":
            self.engine.task_state.add_decision("model requested final")
        elif action == "escalate":
            self.engine.task_state.add_decision("model requested escalation")

        while (
            str(decision.get("action", "")) == "escalate"
            and self.engine._repair_required
            and self.engine._repair_deferrals < 2
        ):
            self.engine._repair_deferrals += 1
            retry_messages = list(messages)
            retry_messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(decision, ensure_ascii=False),
                }
            )
            retry_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Escalation deferred: the latest edit or validation failed. "
                        "Use the failure/tool evidence already in context to repair the "
                        "workspace, then run validation again. Escalate only after bounded "
                        "repair attempts fail."
                    ),
                }
            )
            decision = self.inner.json_completion(retry_messages, schema, **kwargs)
        return decision


class AgentEngine(BaseAgentEngine):
    """Agent loop with mutation rollback and weak-model repair guardrails."""

    def __init__(self, model_key: str | None = None):
        super().__init__(model_key=model_key)
        self._repair_required = False
        self._repair_deferrals = 0
        self._mutations_since_validation = 0
        profile = get_model_profile(self.model_key)
        self.context_manager_config = ContextManagerConfig(
            context_window_tokens=profile.preferred_context,
            reserve_output_tokens=768,
            reserve_state_tokens=768,
            trigger_ratio=0.72,
            keep_recent_messages=6,
        )
        self.task_state = TaskState.from_task(
            "",
            acceptance_criteria=[
                "Complete the requested change or exit safely with evidence.",
                "Preserve unrelated existing work.",
                "Relevant verification must pass before completion.",
            ],
        )
        self._last_context_compaction = None

    @staticmethod
    def _preexisting_changed_paths(status_result: dict[str, Any]) -> set[str]:
        return preexisting_changed_paths(status_result)

    @staticmethod
    def _compact_result(result: dict[str, Any], limit: int = 5000) -> str:
        safe_result = clean_model_result("read_file", result)
        text = json.dumps(safe_result, ensure_ascii=False)
        if len(text) <= limit:
            return text
        return text[:limit] + "...<TRUNCATED>"

    def _deterministic_retrieval_actions(
        self,
        *,
        task: str,
        repo_path: str,
        prepared: dict,
    ) -> list[dict[str, Any]]:
        plan = getattr(self, "retrieval_plan", None)
        if plan is None:
            return []
        return [
            {
                "tool": str(action.get("tool", "")),
                "args": dict(action.get("args") or {}),
            }
            for action in plan.initial_actions
            if action.get("tool")
        ]

    def _run_tool(
        self,
        *,
        repo_path: str,
        task: str,
        name: str,
        args: dict[str, Any],
        progress,
    ) -> dict[str, Any]:
        sandbox_policy = getattr(self, "sandbox_policy", None)
        definition = TOOLS.get(name)
        if sandbox_policy is not None and definition is not None:
            sandbox_decision = sandbox_policy.authorize(
                tool=name,
                risk=definition.risk,
                args=args,
            )
            if not sandbox_decision.allowed:
                self.task_state.add_decision(f"sandbox denied {name}")
                self.task_state.set_next_action(
                    f"replan without sandbox-denied tool {name}"
                )
                self._emit(progress, f"[Sandbox] denied {name}")
                return {
                    "error": sandbox_decision.reason,
                    "sandbox_denied": True,
                    "sandbox_mode": sandbox_policy.mode.value,
                    "tool": name,
                    "risk": definition.risk.value,
                }

        permission_controller = getattr(self, "permission_controller", None)
        if permission_controller is not None and definition is not None:
            decision = permission_controller.authorize(
                repo_path=repo_path,
                tool=name,
                risk=definition.risk,
                args=args,
            )
            if not decision.allowed:
                self.task_state.add_decision(f"permission denied for {name}")
                self.task_state.set_next_action(
                    f"replan without denied tool {name}"
                )
                self._emit(progress, f"[Permission] denied {name}")
                return {
                    "error": decision.reason,
                    "permission_denied": True,
                    "tool": name,
                    "risk": definition.risk.value,
                }

        if name == "find_symbol":
            self._emit(progress, "[Agent] find_symbol")
            symbol = str(args.get("name", "")).strip()
            result = {"matches": find_symbol(repo_path, symbol)}
            for match in result["matches"][:6]:
                path = match.get("path")
                if path:
                    self.task_state.pin_file(str(path))
            self.task_state.set_next_action(f"inspect references for symbol {symbol}")
            return result
        if name == "find_references":
            self._emit(progress, "[Agent] find_references")
            symbol = str(args.get("name", "")).strip()
            result = {"matches": find_references(repo_path, symbol)}
            for match in result["matches"][:8]:
                path = match.get("path")
                if path:
                    self.task_state.pin_file(str(path))
            return result
        if name == "get_symbol_source":
            self._emit(progress, "[Agent] get_symbol_source")
            symbol = str(args.get("name", "")).strip()
            context_lines = int(args.get("context_lines", 1))
            matches = get_symbol_source(
                repo_path,
                symbol,
                context_lines=context_lines,
            )
            for match in matches[:6]:
                path = match.get("path")
                if path:
                    self.task_state.pin_file(str(path))
            self.task_state.set_next_action(
                f"use exact definition source for {symbol}"
            )
            return {"matches": matches}

        if name == "get_reference_context":
            self._emit(progress, "[Agent] get_reference_context")
            symbol = str(args.get("name", "")).strip()
            context_lines = int(args.get("context_lines", 2))
            limit = int(args.get("limit", 12))
            matches = get_reference_context(
                repo_path,
                symbol,
                context_lines=context_lines,
                limit=limit,
            )
            for match in matches[:8]:
                path = match.get("path")
                if path:
                    self.task_state.pin_file(str(path))
            return {"matches": matches}

        if name == "related_files":
            self._emit(progress, "[Agent] related_files")
            query = str(args.get("task", task))
            limit = int(args.get("limit", 8))
            result = {"files": related_files(repo_path, query, limit=limit)}
            for row in result["files"][:8]:
                path = row.get("path")
                if path:
                    self.task_state.pin_file(str(path))
            return result

        if name in WORKSPACE_MUTATING_TOOLS:
            raw_path = args.get("path")
            if isinstance(raw_path, str) and raw_path:
                normalized_path = raw_path.replace("\\", "/")
                candidate = (Path(repo_path).resolve() / normalized_path).resolve()
                likely_change_files = set(
                    getattr(
                        getattr(self, "retrieval_plan", None),
                        "likely_change_files",
                        [],
                    )
                )
                write_scope = list(getattr(self, "_write_scope", []) or [])
                if write_scope and not any(
                    fnmatch(normalized_path, pattern)
                    for pattern in write_scope
                ):
                    self._repair_required = True
                    self.task_state.record_failure(
                        f"mutation outside user write scope: {normalized_path}"
                    )
                    return {
                        "error": (
                            "Mutation blocked outside the user-defined write scope. "
                            f"Allowed patterns: {write_scope}"
                        ),
                        "path": normalized_path,
                        "write_scope_blocked": True,
                    }

                if (
                    is_test_path(normalized_path)
                    and not task_explicitly_allows_test_changes(task, normalized_path)
                ):
                    self._repair_required = True
                    self.task_state.record_failure(
                        f"test mutation blocked outside explicit user intent: {normalized_path}"
                    )
                    return {
                        "error": (
                            "Mutation blocked: tests are verification evidence for this task. "
                            "The user did not explicitly ask Locdex to add/change/fix tests."
                        ),
                        "path": normalized_path,
                        "change_surface_blocked": True,
                    }

                if (
                    candidate.exists()
                    and likely_change_files
                    and normalized_path not in likely_change_files
                    and not task_explicitly_names_change(task, normalized_path)
                ):
                    self._repair_required = True
                    self.task_state.record_failure(
                        f"mutation outside planned change surface: {normalized_path}"
                    )
                    return {
                        "error": (
                            "Mutation blocked outside the planned change surface. "
                            f"Allowed existing files: {sorted(likely_change_files)}"
                        ),
                        "path": normalized_path,
                        "change_surface_blocked": True,
                    }

                journal = getattr(self, "change_journal", None)
                if journal is not None:
                    journal.capture(normalized_path)

        snapshot = snapshot_file(
            repo_path,
            name,
            args,
            set(WORKSPACE_MUTATING_TOOLS),
        )

        if name == "write_file" and snapshot is not None:
            path, previous = snapshot
            if previous is not None and not bool(args.get("overwrite", False)):
                try:
                    current_source = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    current_source = ""
                self._repair_required = True
                self.task_state.record_failure("write_file rejected for existing file")
                self.task_state.pin_file(str(args.get("path", "")))
                return {
                    "error": (
                        "write_file cannot replace an existing file without overwrite=true. "
                        "Use replace_in_file with exact current text instead."
                    ),
                    "path": str(args.get("path", "")),
                    "current_source": current_source[:5000],
                }

        result = super()._run_tool(
            repo_path=repo_path,
            task=task,
            name=name,
            args=args,
            progress=progress,
        )
        guarded = guard_mutation_result(
            repo_path,
            name,
            args,
            result,
            snapshot,
        )

        if "error" in guarded and name in WORKSPACE_MUTATING_TOOLS:
            self._repair_required = True
            self.task_state.record_failure(f"{name} mutation rejected")
            path_text = guarded.get("path") or args.get("path")
            if isinstance(path_text, str):
                candidate = (Path(repo_path).resolve() / path_text).resolve()
                try:
                    current = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    current = ""
                if current:
                    guarded["current_source"] = current[:5000]
                    guarded["repair_hint"] = (
                        "Use the current_source exactly. Prefer a small replace_in_file edit."
                    )
        elif name == "run_tests":
            passed = guarded.get("ok") is True
            self._repair_required = not passed
            self._mutations_since_validation = 0
            if passed:
                self.task_state.mark_validation(True)
            else:
                output = str(guarded.get("output", ""))
                identifiers = []
                for line in output.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(("FAILED ", "ERROR ")):
                        identifiers.append(stripped[:240])
                    if len(identifiers) >= 4:
                        break
                detail = "; ".join(identifiers) or (
                    f"run_tests failed with returncode={guarded.get('returncode')}"
                )
                self.task_state.mark_validation(False, detail)
        elif (
            name in WORKSPACE_MUTATING_TOOLS
            and guarded.get("ok") is True
        ):
            self._mutations_since_validation += 1
            path = guarded.get("path") or args.get("path")
            if path:
                self.task_state.mark_modified(str(path))
                journal = getattr(self, "change_journal", None)
                if journal is not None:
                    journal.record_success(str(path))

        if name == "read_file" and guarded.get("path"):
            self.task_state.pin_file(str(guarded["path"]))
            self.task_state.set_next_action(
                f"use exact source from {guarded['path']} for the next decision"
            )

        return guarded

    def execute(
        self,
        task: str,
        repo_path: str = ".",
        *,
        max_steps: int = 6,
        routing_mode: str = "balanced",
        session: Any | None = None,
        progress=None,
        write_scope: list[str] | None = None,
        permission_controller: PermissionController | None = None,
        sandbox_mode: str | SandboxMode = SandboxMode.WORKSPACE_WRITE,
    ) -> dict:
        self._repair_required = False
        self._repair_deferrals = 0
        self._mutations_since_validation = 0
        self.permission_controller = permission_controller
        self.sandbox_policy = SandboxPolicy(sandbox_mode)
        self.sandbox_mode = self.sandbox_policy.mode.value
        self.verifier.permission_controller = permission_controller
        self._write_scope = [
            str(pattern).replace("\\", "/")
            for pattern in (write_scope or [])
            if str(pattern).strip()
        ]
        self.change_journal = ChangeJournal(repo_path)
        self.task_state = TaskState.from_task(
            task,
            acceptance_criteria=[
                "Complete the requested change or exit safely with evidence.",
                "Preserve unrelated existing work.",
                "Relevant verification must pass before completion.",
            ],
        )
        self.retrieval_plan = plan_retrieval(
            repo_path,
            task,
            max_files=8,
            source_tokens=1800,
        )
        self._preloaded_paths = {
            str(action.get("args", {}).get("path"))
            for action in self.retrieval_plan.initial_actions
            if action.get("tool") == "read_file"
            and action.get("args", {}).get("path")
        }
        for row in self.retrieval_plan.primary_files:
            path = row.get("path")
            if path:
                self.task_state.pin_file(str(path))
        for path in self.retrieval_plan.likely_change_files:
            self.task_state.pin_file(path)
        for missing in self.retrieval_plan.missing_symbols:
            self.task_state.add_decision(
                f"missing local symbol {missing.name} expected in {missing.target_path}"
            )
        if self.retrieval_plan.missing_symbols:
            first = self.retrieval_plan.missing_symbols[0]
            self.task_state.set_next_action(
                f"implement or repair {first.name} in {first.target_path} using exact evidence"
            )
        elif self.retrieval_plan.likely_change_files:
            self.task_state.set_next_action(
                f"inspect exact source in {self.retrieval_plan.likely_change_files[0]}"
            )
        self._last_context_compaction = None

        inner = session or LlamaCppSession(
            model_key=self.model_key,
            hardware=detect_hardware(),
        )
        guarded_session = _RepairAwareSession(inner, self)

        result = super().execute(
            task,
            repo_path,
            max_steps=max_steps,
            routing_mode=routing_mode,
            session=guarded_session,
            progress=progress,
        )

        attempted_modified = set(result.get("files_modified") or [])
        preexisting = set(result.get("preexisting_changes") or [])
        result["attempted_files_modified"] = sorted(attempted_modified)
        result["change_journal"] = self.change_journal.summary()

        if result.get("status") != "completed":
            restored = self.change_journal.rollback()
            result["rollback_performed"] = bool(restored)
            result["rolled_back_files"] = restored
            result["files_modified"] = []
            result["preexisting_changes_touched"] = sorted(
                preexisting & attempted_modified
            )
            result["preexisting_changes"] = sorted(preexisting)
        else:
            result["rollback_performed"] = False
            result["rolled_back_files"] = []
            result["preexisting_changes_touched"] = sorted(
                preexisting & attempted_modified
            )
            result["preexisting_changes"] = sorted(
                preexisting - attempted_modified
            )

        result["task_state"] = self.task_state.to_prompt()
        result["sandbox_mode"] = self.sandbox_policy.mode.value
        result["retrieval_plan"] = self.retrieval_plan.to_dict()
        result["context_compactions"] = self.task_state.compactions
        if self._last_context_compaction is not None:
            result["context_tokens_before"] = self._last_context_compaction.before_tokens
            result["context_tokens_after"] = self._last_context_compaction.after_tokens
        return result
