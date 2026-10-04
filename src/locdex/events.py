from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class AgentEvent:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "timestamp": self.timestamp,
            "data": dict(self.data),
        }


EventSink = Callable[[AgentEvent], None]


class EventBus:
    def __init__(self):
        self._subscribers: list[EventSink] = []
        self._history: list[AgentEvent] = []

    def subscribe(self, sink: EventSink) -> None:
        if sink not in self._subscribers:
            self._subscribers.append(sink)

    def emit(self, kind: str, **data: Any) -> AgentEvent:
        event = AgentEvent(kind=kind, data=data)
        self._history.append(event)
        for sink in list(self._subscribers):
            sink(event)
        return event

    @property
    def history(self) -> list[AgentEvent]:
        return list(self._history)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._history]
