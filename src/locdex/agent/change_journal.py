from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JournalEntry:
    path: str
    existed: bool
    before: bytes | None
    before_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "existed": self.existed,
            "before_sha256": self.before_sha256,
        }


class ChangeJournal:
    """Task-local mutation journal independent of Git.

    The first pre-mutation state of each path is retained so an incomplete or
    escalated task can restore the exact user workspace state from task start.
    """

    def __init__(self, repo_path: str):
        self.root = Path(repo_path).resolve()
        self._entries: dict[str, JournalEntry] = {}
        self._mutation_order: list[str] = []

    def _resolve(self, path: str) -> tuple[str, Path] | None:
        candidate = (self.root / path).resolve()
        try:
            relative = str(candidate.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return None
        return relative, candidate

    def capture(self, path: str) -> JournalEntry | None:
        resolved = self._resolve(path)
        if resolved is None:
            return None
        relative, candidate = resolved

        existing = self._entries.get(relative)
        if existing is not None:
            return existing

        if candidate.is_file():
            try:
                before = candidate.read_bytes()
            except OSError:
                return None
            digest = hashlib.sha256(before).hexdigest()
            entry = JournalEntry(
                path=relative,
                existed=True,
                before=before,
                before_sha256=digest,
            )
        else:
            entry = JournalEntry(
                path=relative,
                existed=False,
                before=None,
                before_sha256=None,
            )

        self._entries[relative] = entry
        return entry

    def record_success(self, path: str) -> None:
        resolved = self._resolve(path)
        if resolved is None:
            return
        relative, _ = resolved
        if relative not in self._entries:
            self.capture(relative)
        if relative not in self._mutation_order:
            self._mutation_order.append(relative)

    @property
    def touched_paths(self) -> list[str]:
        return list(self._mutation_order)

    def rollback(self) -> list[str]:
        restored: list[str] = []
        for relative in reversed(self._mutation_order):
            entry = self._entries.get(relative)
            if entry is None:
                continue
            candidate = (self.root / relative).resolve()
            try:
                if entry.existed:
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    candidate.write_bytes(entry.before or b"")
                elif candidate.is_file():
                    candidate.unlink()
                restored.append(relative)
            except OSError:
                continue
        return sorted(set(restored))

    def summary(self) -> list[dict[str, Any]]:
        return [
            self._entries[path].to_dict()
            for path in self._mutation_order
            if path in self._entries
        ]
