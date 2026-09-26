from __future__ import annotations

from types import SimpleNamespace

from locdex import agent, agent_tools, memory


class FakeRuntime:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def json_completion(self, messages, schema):
        del messages, schema
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return decision


def test_edit_task_cannot_false_complete_without_mutation(monkeypatch, tmp_path):
    runtime = FakeRuntime(
        [
            {"action": "final", "summary": "Fixed it.", "confidence": 1.0},
            {"action": "final", "summary": "Still fixed.", "confidence": 1.0},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda config: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Fix the failing multiplication test.",
        repo_path=str(tmp_path),
        config=SimpleNamespace(max_agent_steps=2),
    )

    assert result["status"] == "incomplete"
    assert runtime.calls == 2


def test_edit_task_requires_mutation_then_requested_validation(monkeypatch, tmp_path):
    runtime = FakeRuntime(
        [
            {"action": "final", "summary": "Fixed it.", "confidence": 1.0},
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "calculator.py", "old": "a + b", "new": "a * b"},
            },
            {"action": "final", "summary": "Fixed it.", "confidence": 1.0},
            {"action": "tool", "tool": "run_tests", "args": {}},
            {"action": "final", "summary": "Fixed and tested.", "confidence": 1.0},
        ]
    )

    def fake_execute_tool(repo_path, name, args):
        del repo_path, args
        if name == "replace_in_file":
            return {"ok": True, "path": "calculator.py", "replacements": 1}
        if name == "run_tests":
            return {"ok": True, "returncode": 0, "output": "2 passed"}
        raise AssertionError(name)

    monkeypatch.setattr(agent, "get_runtime", lambda config: runtime)
    monkeypatch.setattr(agent, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Fix the failing multiplication test and run the tests.",
        repo_path=str(tmp_path),
        config=SimpleNamespace(max_agent_steps=6),
    )

    assert result["status"] == "completed"
    assert [call["tool"] for call in result["tool_calls"]] == ["replace_in_file", "run_tests"]
    assert runtime.calls == 5


def test_run_tests_detects_test_files_without_pytest_config(monkeypatch, tmp_path):
    (tmp_path / "test_example.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    captured = {}

    def fake_run_command(repo_path, argv, cwd=".", timeout=120):
        captured["repo_path"] = repo_path
        captured["argv"] = argv
        captured["cwd"] = cwd
        captured["timeout"] = timeout
        return {"ok": True, "returncode": 0, "output": "1 passed"}

    monkeypatch.setattr(agent_tools, "run_command", fake_run_command)

    result = agent_tools.run_tests(str(tmp_path))

    assert result["ok"] is True
    assert captured["argv"] == ["python", "-m", "pytest", "-q"]


def test_default_memory_database_uses_app_data_not_cwd(monkeypatch, tmp_path):
    app_data = tmp_path / "appdata"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(memory, "user_data_dir", lambda appname, appauthor: str(app_data))

    conn = memory.init_db()
    conn.close()

    assert (app_data / "agent_memory.db").exists()
    assert not (workspace / "agent_memory.db").exists()
