"""Cross-branch multi-agent scheduling and practical no-model orchestration tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from locdex.cli.app import cli
from locdex.cli.welcome import welcome_panel
from locdex.multiagent import parse_agent_spec, plan_agents, AgentSpecError
from locdex.multiagent import supervisor, worktrees


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Locdex Test")
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "app.py")
    _git(root, "commit", "-m", "base")
    return root


def _spec(*agents):
    return parse_agent_spec({"agents": [
        {"name": name, "task": name, "model": "smoke", "permission_mode": "auto-edit",
         "sandbox_mode": "workspace-write", "depends_on": depends}
        for name, depends in agents
    ]})


def test_plan_has_deterministic_parallel_waves_without_model_or_git(tmp_path, monkeypatch):
    spec = _spec(("root", []), ("left", ["root"]), ("right", ["root"]), ("join", ["left", "right"]))
    monkeypatch.setattr(supervisor, "model_status", lambda *args: pytest.fail("loaded model"))
    monkeypatch.setattr(worktrees, "create_agent_worktree", lambda *args, **kwargs: pytest.fail("worktree"))
    plan = plan_agents(spec, parallel=2)
    assert plan["dry_run"] is True
    assert [ [a["name"] for a in wave["agents"]] for wave in plan["waves"]] == [
        ["root"], ["left", "right"], ["join"]
    ]
    assert plan["model_loading"] is False
    assert plan["worktrees_created"] is False


def test_plan_rejects_oversubscribed_concurrency():
    spec = _spec(("worker", []))
    with pytest.raises(supervisor.MultiAgentError, match="between 1 and 8"):
        plan_agents(spec, parallel=9)
    with pytest.raises(supervisor.MultiAgentError, match="between 1 and 8"):
        plan_agents(spec, parallel=0)


def test_cli_plan_outputs_waves_without_running_models(tmp_path, capsys):
    import yaml
    config = tmp_path / "agents.yaml"
    config.write_text(yaml.safe_dump({
        "agents": [
            {"name": "implement", "task": "Implement", "model": "smoke"},
            {"name": "verify", "task": "Verify", "model": "smoke",
             "depends_on": ["implement"]},
        ],
    }), encoding="utf-8")
    assert cli(["agents", "plan", "--config", str(config), "--parallel", "2"]) == 0
    stdout = capsys.readouterr().out
    assert "Wave 1: implement" in stdout
    assert "Wave 2: verify" in stdout
    assert "no models loaded" in stdout


@pytest.mark.parametrize("scope", ["../other/**", "/etc/*", "C:/Windows/**", "src/../../secrets"])
def test_write_scope_rejects_escaping_paths(scope):
    with pytest.raises(AgentSpecError, match="relative"):
        parse_agent_spec({
            "agents": [{"name": "worker", "task": "Fix code", "model": "smoke",
                        "write_scope": [scope]}]
        })


def test_same_upstream_content_in_two_dependencies_is_inherited(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setattr(worktrees, "user_cache_dir", lambda *a, **k: str(tmp_path / "cache"))
    monkeypatch.setattr(supervisor, "model_status", lambda *a: {"installed": True})
    observed = {}

    def fake_execute(engine, task, repo_path, **kwargs):
        path = Path(repo_path) / "app.py"
        if task == "root":
            path.write_text("VALUE = 2\n", encoding="utf-8")
        if task == "join":
            observed["value"] = path.read_text(encoding="utf-8")
        return {"status": "completed", "model": "smoke", "steps": 1, "summary": task,
                "files_modified": ["app.py"] if task == "root" else []}

    monkeypatch.setattr(supervisor, "execute_with_escalation", fake_execute)
    spec = _spec(("root", []), ("left", ["root"]), ("right", ["root"]),
                 ("join", ["left", "right"]))
    result = supervisor.run_agents(spec, str(repo), parallel=2)
    assert result["agents_completed"] == 4
    assert observed["value"] == "VALUE = 2\n"
    assert result["integration_conflicts"] == {}


def test_divergent_parallel_edits_block_join(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setattr(worktrees, "user_cache_dir", lambda *a, **k: str(tmp_path / "cache"))
    monkeypatch.setattr(supervisor, "model_status", lambda *a: {"installed": True})

    def fake_execute(engine, task, repo_path, **kwargs):
        if task in ("left", "right"):
            (Path(repo_path) / "app.py").write_text(f"VALUE = '{task}'\n", encoding="utf-8")
        return {"status": "completed", "steps": 1,
                "files_modified": ["app.py"] if task in ("left", "right") else []}

    monkeypatch.setattr(supervisor, "execute_with_escalation", fake_execute)
    spec = _spec(("left", []), ("right", []), ("join", ["left", "right"]))
    result = supervisor.run_agents(spec, str(repo), parallel=2)
    assert result["agents_completed"] == 2
    assert result["agents"][-1]["result"]["status"] == "blocked"
    assert "app.py" in result["integration_conflicts"]


def test_ancestor_then_descendant_can_intentionally_edit_same_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setattr(worktrees, "user_cache_dir", lambda *a, **k: str(tmp_path / "cache"))
    monkeypatch.setattr(supervisor, "model_status", lambda *a: {"installed": True})

    def fake_execute(engine, task, repo_path, **kwargs):
        path = Path(repo_path) / "app.py"
        if task == "root":
            path.write_text("VALUE = 2\n", encoding="utf-8")
        else:
            assert path.read_text(encoding="utf-8") == "VALUE = 2\n"
            path.write_text("VALUE = 3\n", encoding="utf-8")
        return {"status": "completed", "steps": 1, "files_modified": ["app.py"]}

    monkeypatch.setattr(supervisor, "execute_with_escalation", fake_execute)
    result = supervisor.run_agents(_spec(("root", []), ("finish", ["root"])), str(repo))
    assert result["agents_completed"] == 2
    assert result["integration_conflicts"] == {}


def test_welcome_panel_is_readable_on_wide_and_narrow_terminals():
    wide = welcome_panel(repo_path="/code/example", model="smoke",
                         permission_mode="ask", sandbox_mode="workspace-write",
                         columns=100)
    assert "Welcome to Locdex v" in wide
    assert "Workspace  example" in wide
    assert "\033[" not in wide
    assert "╭" in wide
    narrow = welcome_panel(repo_path="/code/example", model="smoke",
                           permission_mode="ask", sandbox_mode="workspace-write",
                           columns=32)
    assert "Locdex v" in narrow
    assert "Model: smoke" in narrow
    assert "╭" not in narrow
