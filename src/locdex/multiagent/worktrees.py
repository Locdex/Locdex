from __future__ import annotations

import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_dir


class WorktreeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentWorkspace:
    name: str
    branch: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "branch": self.branch,
            "path": self.path,
        }


def _git(repo_path: str, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=Path(repo_path).resolve(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise WorktreeError("git is required for multi-agent worktrees.") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeError("git worktree operation timed out.") from exc


def repository_root(repo_path: str) -> Path:
    process = _git(repo_path, "rev-parse", "--show-toplevel")
    if process.returncode != 0:
        raise WorktreeError("Multi-agent runs require a Git repository.")
    return Path(process.stdout.strip()).resolve()


def ensure_clean_repository(repo_path: str) -> None:
    root = repository_root(repo_path)
    process = _git(str(root), "status", "--porcelain")
    if process.returncode != 0:
        raise WorktreeError(process.stderr.strip() or "Could not read Git status.")
    if process.stdout.strip():
        raise WorktreeError(
            "Multi-agent runs currently require a clean base working tree. "
            "Commit/stash existing changes or use a clean clone first."
        )


def new_run_id() -> str:
    return uuid.uuid4().hex[:10]


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return cleaned or "agent"


def create_agent_worktree(
    repo_path: str,
    *,
    agent_name: str,
    run_id: str,
    base_ref: str = "HEAD",
) -> AgentWorkspace:
    root = repository_root(repo_path)
    slug = _slug(agent_name)
    branch = f"locdex/agent/{run_id}-{slug}"
    worktree_root = (
        Path(user_cache_dir("locdex", "Locdex"))
        / "agent-runs"
        / run_id
        / slug
    ).expanduser().resolve()
    worktree_root.parent.mkdir(parents=True, exist_ok=True)

    if worktree_root.exists():
        raise WorktreeError(f"Agent worktree already exists: {worktree_root}")

    process = _git(
        str(root),
        "worktree",
        "add",
        "-b",
        branch,
        str(worktree_root),
        base_ref,
    )
    if process.returncode != 0:
        raise WorktreeError(
            process.stderr.strip()
            or process.stdout.strip()
            or f"Could not create worktree for {agent_name}."
        )

    return AgentWorkspace(
        name=agent_name,
        branch=branch,
        path=str(worktree_root),
    )
