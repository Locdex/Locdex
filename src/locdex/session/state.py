from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sessions_dir() -> Path:
    root = Path(user_cache_dir("locdex", "Locdex")).expanduser().resolve()
    path = root / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class SessionTask:
    task: str
    status: str
    model: str
    sandbox_mode: str
    permission_mode: str
    summary: str
    files_modified: list[str] = field(default_factory=list)
    verification_passed: bool | None = None
    checkpoint_id: str | None = None
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionState:
    session_id: str
    repo_path: str
    model: str
    permission_mode: str = "ask"
    sandbox_mode: str = "workspace-network"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    tasks: list[SessionTask] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    latest_diff: str = ""
    latest_checkpoint_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        repo_path: str,
        model: str,
        permission_mode: str = "ask",
        sandbox_mode: str = "workspace-network",
    ) -> "SessionState":
        return cls(
            session_id=uuid.uuid4().hex[:12],
            repo_path=str(Path(repo_path).resolve()),
            model=model,
            permission_mode=permission_mode,
            sandbox_mode=sandbox_mode,
        )

    @property
    def path(self) -> Path:
        return sessions_dir() / f"{self.session_id}.json"

    def touch(self) -> None:
        self.updated_at = _now()

    def add_task(self, task: SessionTask) -> None:
        self.tasks.append(task)
        self.latest_checkpoint_id = task.checkpoint_id
        self.touch()

    def add_note(self, text: str) -> None:
        value = text.strip()
        if value:
            self.notes.append(value)
            self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "repo_path": self.repo_path,
            "model": self.model,
            "permission_mode": self.permission_mode,
            "sandbox_mode": self.sandbox_mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tasks": [task.to_dict() for task in self.tasks],
            "notes": list(self.notes),
            "latest_diff": self.latest_diff,
            "latest_checkpoint_id": self.latest_checkpoint_id,
        }

    def save(self) -> Path:
        self.touch()
        self.path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return self.path

    @classmethod
    def load(cls, session_id: str) -> "SessionState":
        path = sessions_dir() / f"{session_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Locdex session not found: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks = [
            SessionTask(**row)
            for row in data.get("tasks", [])
            if isinstance(row, dict)
        ]
        return cls(
            session_id=str(data["session_id"]),
            repo_path=str(data["repo_path"]),
            model=str(data["model"]),
            permission_mode=str(data.get("permission_mode", "ask")),
            sandbox_mode=str(data.get("sandbox_mode", "workspace-network")),
            created_at=str(data.get("created_at", _now())),
            updated_at=str(data.get("updated_at", _now())),
            tasks=tasks,
            notes=[str(item) for item in data.get("notes", [])],
            latest_diff=str(data.get("latest_diff", "")),
            latest_checkpoint_id=data.get("latest_checkpoint_id"),
        )


def list_sessions(limit: int = 20) -> list[SessionState]:
    rows: list[SessionState] = []
    for path in sessions_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append(SessionState.load(str(data["session_id"])))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    rows.sort(key=lambda item: item.updated_at, reverse=True)
    return rows[: max(1, min(int(limit), 100))]
