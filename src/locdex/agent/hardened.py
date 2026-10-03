from __future__ import annotations

import json
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

    def json_completion(self, messages, schema, **kwargs):
        decision = self.inner.json_completion(messages, schema, **kwargs)
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
        elif name == "run_tests":
            self._repair_required = guarded.get("ok") is not True

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
