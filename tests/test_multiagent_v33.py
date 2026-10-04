from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from locdex.multiagent import AgentSpecError, parse_agent_spec
from locdex.multiagent import supervisor
from locdex.multiagent import worktrees


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Locdex Test")
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_user_defines_agent_tasks_models_and_scopes():
    spec = parse_agent_spec(
        {
            "version": 1,
            "defaults": {
                "model": "qwen25-7b",
                "max_steps": 7,
                "mode": "balanced",
            },
            "agents": [
                {
                    "name": "api-migration",
                    "task": "Migrate the API client.",
                    "write_scope": ["src/api/**"],
                },
                {
                    "name": "docs-check",
                    "task": "Update the migration documentation.",
                    "model": "qwen25-3b",
                    "write_scope": ["docs/**"],
                },
            ],
        }
    )

    assert [agent.name for agent in spec.agents] == ["api-migration", "docs-check"]
    assert spec.agents[0].task == "Migrate the API client."
    assert spec.agents[0].model == "qwen25-7b"
    assert spec.agents[0].write_scope == ("src/api/**",)
    assert spec.agents[1].model == "qwen25-3b"
    assert spec.agents[1].task == "Update the migration documentation."


def test_agent_names_must_be_unique():
    with pytest.raises(AgentSpecError, match="unique"):
        parse_agent_spec(
            {
                "agents": [
                    {"name": "worker", "task": "Task A", "model": "smoke"},
                    {"name": "worker", "task": "Task B", "model": "smoke"},
                ]
            }
        )


def test_unknown_model_is_rejected():
    with pytest.raises(AgentSpecError, match="unknown model"):
        parse_agent_spec(
            {
                "agents": [
                    {
                        "name": "worker",
                        "task": "Do something.",
                        "model": "does-not-exist",
                    }
                ]
            }
        )


def test_supervisor_uses_isolated_worktrees_and_user_scopes(tmp_path, monkeypatch):
    repo = _clean_repo(tmp_path)
    cache = tmp_path / "cache"
    monkeypatch.setattr(worktrees, "user_cache_dir", lambda *args, **kwargs: str(cache))
    monkeypatch.setattr(
        supervisor,
        "model_status",
        lambda key: {"installed": True, "model": key},
    )

    calls: list[dict] = []

    class FakeEngine:
        def __init__(self, model_key=None):
            self.model_key = model_key

        def execute(
            self,
            task,
            repo_path,
            *,
            max_steps,
            routing_mode,
            write_scope,
            progress,
        ):
            calls.append(
                {
                    "model": self.model_key,
                    "task": task,
                    "repo": repo_path,
                    "max_steps": max_steps,
                    "mode": routing_mode,
                    "write_scope": write_scope,
                }
            )
            return {
                "status": "completed",
                "model": self.model_key,
                "summary": "done",
                "steps": 1,
                "files_modified": [],
            }

    monkeypatch.setattr(supervisor, "AgentEngine", FakeEngine)

    spec = parse_agent_spec(
        {
            "agents": [
                {
                    "name": "backend",
                    "task": "Implement backend change.",
                    "model": "qwen25-7b",
                    "write_scope": ["src/backend/**"],
                },
                {
                    "name": "frontend",
                    "task": "Implement frontend change.",
                    "model": "qwen25-3b",
                    "write_scope": ["src/frontend/**"],
                },
            ]
        }
    )

    result = supervisor.run_agents(spec, str(repo), parallel=2)

    assert result["agents_total"] == 2
    assert result["agents_completed"] == 2
    assert result["auto_commit"] is False
    assert result["auto_merge"] is False

    workspaces = [row["workspace"]["path"] for row in result["agents"]]
    branches = [row["workspace"]["branch"] for row in result["agents"]]
    assert len(set(workspaces)) == 2
    assert len(set(branches)) == 2
    assert all(Path(path).is_dir() for path in workspaces)

    by_task = {call["task"]: call for call in calls}
    assert by_task["Implement backend change."]["write_scope"] == ["src/backend/**"]
    assert by_task["Implement frontend change."]["write_scope"] == ["src/frontend/**"]


def test_supervisor_requires_installed_models(tmp_path, monkeypatch):
    repo = _clean_repo(tmp_path)
    monkeypatch.setattr(
        supervisor,
        "model_status",
        lambda key: {"installed": False, "model": key},
    )
    spec = parse_agent_spec(
        {
            "agents": [
                {"name": "worker", "task": "Inspect app.", "model": "qwen25-3b"}
            ]
        }
    )

    with pytest.raises(supervisor.MultiAgentError, match="model install"):
        supervisor.run_agents(spec, str(repo))
