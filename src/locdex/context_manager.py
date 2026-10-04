from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .context import estimate_tokens
from .task_state import TaskState


@dataclass(frozen=True)
class ContextManagerConfig:
    context_window_tokens: int = 8192
    reserve_output_tokens: int = 1024
    reserve_state_tokens: int = 1024
    trigger_ratio: float = 0.72
    keep_recent_messages: int = 6


@dataclass(frozen=True)
class ContextManagerResult:
    messages: list[dict[str, str]]
    compacted: bool
    before_tokens: int
    after_tokens: int


def estimate_messages_tokens(messages: Iterable[dict[str, str]]) -> int:
    total = 0
    for message in messages:
        total += estimate_tokens(str(message.get("role", "")))
        total += estimate_tokens(str(message.get("content", "")))
        total += 4
    return total


def _recent_messages(
    messages: list[dict[str, str]],
    keep: int,
) -> list[dict[str, str]]:
    candidates = [
        {"role": str(message.get("role", "user")), "content": str(message.get("content", ""))}
        for message in messages
        if message.get("role") != "system"
    ]
    if keep <= 0:
        return []
    return candidates[-keep:]


def maybe_compact(
    messages: list[dict[str, str]],
    task_state: TaskState,
    config: ContextManagerConfig | None = None,
) -> ContextManagerResult:
    config = config or ContextManagerConfig()
    before = estimate_messages_tokens(messages)

    usable = max(
        512,
        config.context_window_tokens
        - config.reserve_output_tokens
        - config.reserve_state_tokens,
    )
    trigger = max(256, int(usable * config.trigger_ratio))
    if before < trigger:
        return ContextManagerResult(
            messages=list(messages),
            compacted=False,
            before_tokens=before,
            after_tokens=before,
        )

    system_messages = [
        {"role": "system", "content": str(message.get("content", ""))}
        for message in messages
        if message.get("role") == "system"
    ]
    system = system_messages[:1]

    state_message = {
        "role": "user",
        "content": (
            task_state.to_prompt()
            + "\n\nRECENT WORK follows. Older tool output and stale file contents were compacted."
        ),
    }
    recent = _recent_messages(messages, config.keep_recent_messages)

    compacted = [*system, state_message, *recent]
    after = estimate_messages_tokens(compacted)

    # If the recent slice is still too large, deterministically drop oldest
    # recent messages until the working set fits the usable budget.
    while len(compacted) > len(system) + 1 and after > usable:
        del compacted[len(system) + 1]
        after = estimate_messages_tokens(compacted)

    task_state.note_compaction()
    return ContextManagerResult(
        messages=compacted,
        compacted=True,
        before_tokens=before,
        after_tokens=after,
    )
