from __future__ import annotations

import json
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
from ..task_state import TaskState
from .engine import AgentEngine as BaseAgentEngine
from .guards import (
    clean_model_result,
    guard_mutation_result,
    preexisting_changed_paths,
    snapshot_file,
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

        args = decision.get("args") if isinstance(decision.get("args"), dict) else {}
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
        signature = json.dumps(
            {
                "action": decision.get("action"),
                "tool": decision.get("tool"),
                "args": args,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        self._signature_counts[signature] = self._signature_counts.get(signature, 0) + 1

        if (
            self._signature_counts[signature] >= 2
            and str(decision.get("action", "")) == "tool"
        ):
            path = args.get("path")
            if isinstance(path, str) and path:
                return {
                    "action": "tool",
                    "tool": "read_file",
                    "args": {"path": path, "start_line": 1, "end_line": 300},
                    "summary": "Refresh exact source after a repeated edit attempt.",
                    "confidence": 1.0,
                }

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
                        "The exact same tool call has already been attempted. "
                        "Choose a materially different action or run validation."
                    ),
                }
            )
            decision = self.inner.json_completion(retry_messages, schema, **kwargs)

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
    ) -> dict:
        self._repair_required = False
        self._repair_deferrals = 0
        self._mutations_since_validation = 0
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

        modified = set(result.get("files_modified") or [])
        preexisting = set(result.get("preexisting_changes") or [])
        result["preexisting_changes_touched"] = sorted(preexisting & modified)
        result["preexisting_changes"] = sorted(preexisting - modified)
        result["task_state"] = self.task_state.to_prompt()
        result["retrieval_plan"] = self.retrieval_plan.to_dict()
        result["context_compactions"] = self.task_state.compactions
        if self._last_context_compaction is not None:
            result["context_tokens_before"] = self._last_context_compaction.before_tokens
            result["context_tokens_after"] = self._last_context_compaction.after_tokens
        return result
