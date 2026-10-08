from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContextItem:
    level: str
    label: str
    content: str
    tokens: int
    fingerprint: str | None = None


@dataclass
class ContextPack:
    items: list[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    redactions: int = 0

    def add(self, item: ContextItem) -> None:
        self.items.append(item)
        self.total_tokens += item.tokens
