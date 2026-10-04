from __future__ import annotations

from ..intelligence import build_repo_map, graph_summary, task_context_text
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

        # Conservative char cap for v1; ContextManager performs another
        # model-specific prompt budget check later.
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

        # Highest-value context first: relationships and exact task source.
        graph_budget = min(1400, remaining())
        if graph_budget:
            self._add_bounded(
                pack,
                level="metadata",
                label="repo_graph",
                content=graph_summary(repo_path, task, limit=12),
                token_cap=graph_budget,
                cloud=cloud,
            )

        source_budget = min(2200, remaining())
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

        # Broad inventory is useful, but should never crowd out the targeted
        # graph/source context above.
        repo = build_repo_map(repo_path)
        summary_lines: list[str] = []
        for row in repo[:200]:
            symbol_text = ", ".join(row["symbols"][:12])
            summary_lines.append(f"{row['path']} :: {symbol_text}")
        repo_map = "\n".join(summary_lines)

        map_budget = min(1600, remaining())
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
