from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    max_input_tokens: int = 8000
    max_output_tokens: int = 3000
    max_total_task_tokens: int = 20000
    allow_expansion: bool = True


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
