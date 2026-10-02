from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentState:
    objective: str
    phase: str = "understand"
    plan: list[str] = field(default_factory=list)
    attempts: int = 0
    failures: list[str] = field(default_factory=list)
    files_read: set[str] = field(default_factory=set)
    files_modified: set[str] = field(default_factory=set)
    current_diff: str = ""
