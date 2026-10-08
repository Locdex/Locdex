from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ExposureRecord:
    provider: str
    model: str
    policy: str
    context_tokens: int
    redactions: int
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
