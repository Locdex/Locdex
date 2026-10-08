from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderCapabilities:
    prompt_cache: bool = False
    explicit_cache: bool = False
    tools: bool = True
    reasoning_controls: bool = False


class Provider(Protocol):
    name: str
    capabilities: ProviderCapabilities
    def generate(self, messages: list[dict], **kwargs) -> dict: ...
