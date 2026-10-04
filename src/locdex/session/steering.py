from __future__ import annotations

from collections import deque
from threading import Lock


class SteeringQueue:
    """Thread-safe queue of user steering messages for an active agent run."""

    def __init__(self):
        self._items: deque[str] = deque()
        self._lock = Lock()
        self._cancelled = False

    def submit(self, text: str) -> None:
        value = text.strip()
        if not value:
            return
        with self._lock:
            self._items.append(value)

    def drain(self) -> list[str]:
        with self._lock:
            rows = list(self._items)
            self._items.clear()
            return rows

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled
