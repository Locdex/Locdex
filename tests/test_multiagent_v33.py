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
                "permission_mode": "auto-edit",
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
    assert spec.agents[0].permission_mode == "auto-edit"
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

    def fake_execute(engine, task, repo_path, **kwargs):
        calls.append(
            {
                "model": engine.model_key,
                "task": task,
                "repo": repo_path,
                "max_steps": kwargs["max_steps"],
                "mode": kwargs["routing_mode"],
                "write_scope": kwargs["write_scope"],
                "permission_mode": kwargs["permission_controller"].mode.value,
                "sandbox_mode": kwargs["sandbox_mode"],
            }
        )
        return {
            "status": "completed",
            "model": engine.model_key,
            "summary": "done",
            "steps": 1,
            "files_modified": [],
        }

    monkeypatch.setattr(supervisor, "execute_with_escalation", fake_execute)

    spec = parse_agent_spec(
        {
            "agents": [
                {
                    "name": "backend",
                    "task": "Implement backend change.",
                    "model": "qwen25-7b",
                    "write_scope": ["src/backend/**"],
                    "permission_mode": "auto-edit",
                    "sandbox_mode": "workspace-write",
                },
                {
                    "name": "frontend",
                    "task": "Implement frontend change.",
                    "model": "qwen25-3b",
                    "write_scope": ["src/frontend/**"],
                    "permission_mode": "auto-edit",
                    "sandbox_mode": "workspace-write",
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
    assert by_task["Implement backend change."]["permission_mode"] == "auto-edit"
    assert by_task["Implement backend change."]["sandbox_mode"] == "workspace-write"
    assert by_task["Implement frontend change."]["write_scope"] == ["src/frontend/**"]
    assert by_task["Implement frontend change."]["permission_mode"] == "auto-edit"
    assert by_task["Implement frontend change."]["sandbox_mode"] == "workspace-write"


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
                {
                    "name": "worker",
                    "task": "Inspect app.",
                    "model": "qwen25-3b",
                    "permission_mode": "auto-edit",
                }
            ]
        }
    )

    with pytest.raises(supervisor.MultiAgentError, match="model install"):
        supervisor.run_agents(spec, str(repo))


def test_parallel_multiagent_rejects_interactive_ask_mode(tmp_path, monkeypatch):
    repo = _clean_repo(tmp_path)
    monkeypatch.setattr(
        supervisor,
        "model_status",
        lambda key: {"installed": True, "model": key},
    )
    spec = parse_agent_spec(
        {
            "agents": [
                {"name": "a", "task": "Inspect app.", "model": "smoke"},
                {"name": "b", "task": "Inspect app.", "model": "smoke"},
            ]
        }
    )

    with pytest.raises(supervisor.MultiAgentError, match="--parallel 1"):
        supervisor.run_agents(
            spec,
            str(repo),
            parallel=2,
            approval_callback=lambda request: None,
        )


def test_serial_ask_mode_accepts_approval_callback(tmp_path, monkeypatch):
    repo = _clean_repo(tmp_path)
    cache = tmp_path / "cache"
    monkeypatch.setattr(worktrees, "user_cache_dir", lambda *args, **kwargs: str(cache))
    monkeypatch.setattr(
        supervisor,
        "model_status",
        lambda key: {"installed": True, "model": key},
    )

    seen = {}

    def fake_execute(engine, task, repo_path, **kwargs):
        seen["mode"] = kwargs["permission_controller"].mode.value
        seen["callback"] = kwargs["permission_controller"].approval_callback
        return {"status": "completed", "steps": 1, "files_modified": []}

    monkeypatch.setattr(supervisor, "execute_with_escalation", fake_execute)
    callback = lambda request: None
    spec = parse_agent_spec(
        {
            "agents": [
                {"name": "worker", "task": "Inspect app.", "model": "smoke"}
            ]
        }
    )

    result = supervisor.run_agents(
        spec,
        str(repo),
        parallel=1,
        approval_callback=callback,
    )

    assert result["agents_completed"] == 1
    assert seen["mode"] == "ask"
    assert seen["callback"] is callback


def test_agent_dependencies_are_validated():
    spec = parse_agent_spec(
        {
            "agents": [
                {
                    "name": "backend",
                    "task": "Implement backend.",
                    "model": "smoke",
                    "permission_mode": "auto-edit",
                },
                {
                    "name": "tests",
                    "task": "Verify backend.",
                    "model": "smoke",
                    "permission_mode": "auto-edit",
                    "depends_on": ["backend"],
                    "priority": 10,
                    "role": "verifier",
                },
            ]
        }
    )
    assert spec.agents[1].depends_on == ("backend",)
    assert spec.agents[1].role == "verifier"
    assert spec.agents[1].priority == 10

    with pytest.raises(AgentSpecError, match="unknown agents"):
        parse_agent_spec(
            {
                "agents": [
                    {
                        "name": "tests",
                        "task": "Verify.",
                        "model": "smoke",
                        "depends_on": ["missing"],
                    }
                ]
            }
        )

    with pytest.raises(AgentSpecError, match="cycle"):
        parse_agent_spec(
            {
                "agents": [
                    {
                        "name": "a",
                        "task": "A",
                        "model": "smoke",
                        "depends_on": ["b"],
                    },
                    {
                        "name": "b",
                        "task": "B",
                        "model": "smoke",
                        "depends_on": ["a"],
                    },
                ]
            }
        )


def test_dependency_changes_are_inherited_without_commits(tmp_path, monkeypatch):
    repo = _clean_repo(tmp_path)
    cache = tmp_path / "cache"
    monkeypatch.setattr(
        worktrees,
        "user_cache_dir",
        lambda *args, **kwargs: str(cache),
    )
    monkeypatch.setattr(
        supervisor,
        "model_status",
        lambda key: {"installed": True, "model": key},
    )

    observed = {}

    def fake_execute(engine, task, repo_path, **kwargs):
        path = Path(repo_path) / "app.py"
        if task == "Change backend.":
            path.write_text("VALUE = 2\n", encoding="utf-8")
        else:
            observed["downstream_source"] = path.read_text(encoding="utf-8")
        return {
            "status": "completed",
            "model": engine.model_key,
            "summary": task,
            "steps": 1,
            "files_modified": ["app.py"] if task == "Change backend." else [],
        }

    monkeypatch.setattr(
        supervisor,
        "execute_with_escalation",
        fake_execute,
    )
    spec = parse_agent_spec(
        {
            "agents": [
                {
                    "name": "backend",
                    "task": "Change backend.",
                    "model": "smoke",
                    "permission_mode": "auto-edit",
                },
                {
                    "name": "verify",
                    "task": "Inspect backend.",
                    "model": "smoke",
                    "permission_mode": "auto-edit",
                    "depends_on": ["backend"],
                },
            ]
        }
    )

    result = supervisor.run_agents(spec, str(repo), parallel=1)

    assert result["agents_completed"] == 2
    assert observed["downstream_source"] == "VALUE = 2\n"
    assert result["auto_commit"] is False
    assert result["auto_merge"] is False
