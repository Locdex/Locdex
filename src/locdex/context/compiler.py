from __future__ import annotations

from ..intelligence import build_repo_map
from ..security.secrets import redact_secrets
from .budget import ContextBudget, estimate_tokens
from .pack import ContextItem, ContextPack


class ContextCompiler:
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

        repo = build_repo_map(repo_path)
        summary_lines: list[str] = []
        for row in repo[:200]:
            symbol_text = ", ".join(row["symbols"][:12])
            summary_lines.append(f"{row['path']} :: {symbol_text}")

        summary = "\n".join(summary_lines)
        if cloud:
            summary, redactions = redact_secrets(summary)
            pack.redactions += redactions

        remaining = max(0, budget.max_input_tokens - pack.total_tokens)
        if remaining:
            summary = summary[: remaining * 4]
            pack.add(ContextItem("metadata", "repo_map", summary, estimate_tokens(summary)))

        return pack
