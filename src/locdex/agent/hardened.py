from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..runtime import LlamaCppSession, detect_hardware
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

    def _run_tool(
        self,
        *,
        repo_path: str,
        task: str,
        name: str,
        args: dict[str, Any],
        progress,
    ) -> dict[str, Any]:
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
            self._repair_required = guarded.get("ok") is not True
            self._mutations_since_validation = 0
        elif (
            name in WORKSPACE_MUTATING_TOOLS
            and guarded.get("ok") is True
        ):
            self._mutations_since_validation += 1

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
        return result
