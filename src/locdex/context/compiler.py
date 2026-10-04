from __future__ import annotations

from ..intelligence import (
    build_repo_map,
    graph_summary,
    retrieval_plan_text,
    task_context_text,
)
from ..security.secrets import redact_secrets
from .budget import ContextBudget, estimate_tokens
from .pack import ContextItem, ContextPack


class ContextCompiler:
    @staticmethod
    def _add_bounded(
        pack: ContextPack,
        *,
        level: str,
        label: str,
        content: str,
        token_cap: int,
        cloud: bool,
    ) -> None:
        if not content or token_cap <= 0:
            return

        text = content
        if cloud:
            text, redactions = redact_secrets(text)
            pack.redactions += redactions

        text = text[: max(1, token_cap) * 4]
        pack.add(
            ContextItem(
                level,
                label,
                text,
                estimate_tokens(text),
            )
        )

    def compile(
        self,
        repo_path: str,
        task: str,
        budget: ContextBudget | None = None,
        cloud: bool = False,
    ) -> ContextPack:
        budget = budget or ContextBudget()
        pack = ContextPack()

        task_text, redactions = redact_secrets(task) if cloud else (task, 0)
        pack.redactions += redactions
        pack.add(ContextItem("metadata", "task", task_text, estimate_tokens(task_text)))

        def remaining() -> int:
            return max(0, budget.max_input_tokens - pack.total_tokens)

        # Deterministic retrieval intent comes first so the model sees what
        # Locdex has already inferred before it spends a generation planning.
        plan_budget = min(1100, remaining())
        if plan_budget:
            self._add_bounded(
                pack,
                level="metadata",
                label="retrieval_plan",
                content=retrieval_plan_text(
                    repo_path,
                    task,
                    max_files=8,
                    source_tokens=1800,
                ),
                token_cap=plan_budget,
                cloud=cloud,
            )

        # Exact source is more valuable than broad inventory.
        source_budget = min(1900, remaining())
        if source_budget:
            self._add_bounded(
                pack,
                level="exact",
                label="task_source",
                content=task_context_text(
                    repo_path,
                    task,
                    max_tokens=source_budget,
                    max_files=6,
                ),
                token_cap=source_budget,
                cloud=cloud,
            )

        graph_budget = min(1000, remaining())
        if graph_budget:
            self._add_bounded(
                pack,
                level="metadata",
                label="repo_graph",
                content=graph_summary(repo_path, task, limit=12),
                token_cap=graph_budget,
                cloud=cloud,
            )

        # Broad inventory is last and capped so it never crowds out targeted
        # plan/source context.
        repo = build_repo_map(repo_path)
        summary_lines: list[str] = []
        for row in repo[:200]:
            symbol_text = ", ".join(row["symbols"][:12])
            summary_lines.append(f"{row['path']} :: {symbol_text}")
        repo_map = "\n".join(summary_lines)

        map_budget = min(1200, remaining())
        if map_budget:
            self._add_bounded(
                pack,
                level="metadata",
                label="repo_map",
                content=repo_map,
                token_cap=map_budget,
                cloud=cloud,
            )

        return pack
