from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def checkpoints_dir(session_id: str) -> Path:
    root = Path(user_cache_dir("locdex", "Locdex")).expanduser().resolve()
    path = root / "sessions" / "checkpoints" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    session_id: str
    repo_path: str
    created_at: str
    files: list[dict[str, Any]]
    task: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "repo_path": self.repo_path,
            "created_at": self.created_at,
            "task": self.task,
            "files": self.files,
        }


def create_checkpoint(
    *,
    session_id: str,
    repo_path: str,
    journal_payload: list[dict[str, Any]],
    task: str = "",
) -> Checkpoint | None:
    if not journal_payload:
        return None

    checkpoint = Checkpoint(
        checkpoint_id=uuid.uuid4().hex[:12],
        session_id=session_id,
        repo_path=str(Path(repo_path).resolve()),
        created_at=_now(),
        task=task,
        files=list(journal_payload),
    )
    path = checkpoints_dir(session_id) / f"{checkpoint.checkpoint_id}.json"
    path.write_text(
        json.dumps(checkpoint.to_dict(), indent=2),
        encoding="utf-8",
    )
    return checkpoint


def load_checkpoint(session_id: str, checkpoint_id: str) -> Checkpoint:
    path = checkpoints_dir(session_id) / f"{checkpoint_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Checkpoint(
        checkpoint_id=str(data["checkpoint_id"]),
        session_id=str(data["session_id"]),
        repo_path=str(data["repo_path"]),
        created_at=str(data["created_at"]),
        task=str(data.get("task", "")),
        files=list(data.get("files", [])),
    )


def list_checkpoints(session_id: str) -> list[Checkpoint]:
    rows: list[Checkpoint] = []
    for path in checkpoints_dir(session_id).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                Checkpoint(
                    checkpoint_id=str(data["checkpoint_id"]),
                    session_id=str(data["session_id"]),
                    repo_path=str(data["repo_path"]),
                    created_at=str(data["created_at"]),
                    task=str(data.get("task", "")),
                    files=list(data.get("files", [])),
                )
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    rows.sort(key=lambda item: item.created_at, reverse=True)
    return rows


def _decode(value: str | None) -> bytes | None:
    if value is None:
        return None
    return base64.b64decode(value.encode("ascii"))


def _current_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def undo_checkpoint(
    checkpoint: Checkpoint,
    *,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(checkpoint.repo_path).resolve()
    restored: list[str] = []
    conflicts: list[str] = []

    for row in reversed(checkpoint.files):
        relative = str(row["path"])
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            conflicts.append(relative)
            continue

        expected_after = row.get("after_sha256")
        current_sha = _current_sha(candidate)
        if not force and expected_after != current_sha:
            # If both are None, the path is still absent and can be restored.
            if not (expected_after is None and current_sha is None):
                conflicts.append(relative)
                continue

        before_kind = str(row.get("before_kind", "missing"))
        before = _decode(row.get("before_b64"))

        try:
            if before_kind == "file":
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_bytes(before or b"")
            elif before_kind == "directory":
                candidate.mkdir(parents=True, exist_ok=True)
            else:
                if candidate.is_file():
                    candidate.unlink()
                elif candidate.is_dir() and not any(candidate.iterdir()):
                    candidate.rmdir()
            restored.append(relative)
        except OSError:
            conflicts.append(relative)

    return {
        "checkpoint_id": checkpoint.checkpoint_id,
        "restored": sorted(set(restored)),
        "conflicts": sorted(set(conflicts)),
        "forced": force,
        "ok": not conflicts,
    }
