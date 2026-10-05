from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from threading import Lock

from platformdirs import user_cache_dir


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


class PersistentSteeringQueue:
    """Cross-process steering inbox for an active Locdex session."""

    def __init__(self, session_id: str):
        root = Path(user_cache_dir("locdex", "Locdex")).expanduser().resolve()
        self.root = root / "sessions" / "steering"
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self.inbox = self.root / f"{session_id}.jsonl"
        self.cancel_file = self.root / f"{session_id}.cancel"

    def submit(self, text: str) -> None:
        value = text.strip()
        if not value:
            return
        with self.inbox.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"text": value}, ensure_ascii=False) + "\n")

    def drain(self) -> list[str]:
        if not self.inbox.is_file():
            return []
        try:
            lines = self.inbox.read_text(encoding="utf-8").splitlines()
            self.inbox.write_text("", encoding="utf-8")
        except OSError:
            return []

        rows: list[str] = []
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            value = str(payload.get("text", "")).strip()
            if value:
                rows.append(value)
        return rows

    def cancel(self) -> None:
        self.cancel_file.write_text("cancelled\n", encoding="utf-8")

    def reset_cancel(self) -> None:
        try:
            self.cancel_file.unlink()
        except FileNotFoundError:
            pass

    @property
    def cancelled(self) -> bool:
        return self.cancel_file.is_file()
