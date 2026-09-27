from __future__ import annotations

from types import SimpleNamespace

from locdex import agent


class FakeRuntime:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0
        self.schemas = []

    def json_completion(self, messages, schema):
        del messages
        self.schemas.append(schema)
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return decision


def _config(steps=8, model_key="smoke"):
    return SimpleNamespace(max_agent_steps=steps, model_key=model_key)


def test_read_only_task_blocks_workspace_edit(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    runtime = FakeRuntime(
        [
            {"action": "tool", "tool": "write_file", "args": {"path": "app.py", "content": "VALUE = 2\n"}},
            {"action": "final", "summary": "Inspected.", "confidence": 0.8},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Inspect app.py and tell me what it does.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "completed"
    assert "read-only" in result["tool_calls"][0]["result"]["error"]
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_edit_task_authorizes_workspace_write(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    runtime = FakeRuntime(
        [
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "app.py", "old": "VALUE = 1", "new": "VALUE = 2"},
            },
            {"action": "final", "summary": "Updated VALUE.", "confidence": 0.9},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "In app.py, change VALUE from 1 to 2.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "completed"
    assert "VALUE = 2" in (tmp_path / "app.py").read_text(encoding="utf-8")


def test_delete_path_needs_explicit_delete_instruction(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    runtime = FakeRuntime(
        [
            {"action": "tool", "tool": "delete_path", "args": {"path": "app.py"}},
            {"action": "final", "summary": "Done.", "confidence": 0.8},
            {"action": "final", "summary": "Done.", "confidence": 0.8},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "In app.py, fix the VALUE constant.",
        repo_path=str(tmp_path),
        config=_config(steps=4),
    )

    assert result["tool_calls"][0]["tool"] == "delete_path"
    assert "explicit deletion" in result["tool_calls"][0]["result"]["error"]
    assert (tmp_path / "app.py").exists()


def test_two_premature_finals_trigger_constrained_edit_schema(monkeypatch, tmp_path):
    (tmp_path / "config.py").write_text("TIMEOUT = 30\n", encoding="utf-8")

    runtime = FakeRuntime(
        [
            {"action": "final", "summary": "Changed.", "confidence": 0.9},
            {"action": "final", "summary": "Changed.", "confidence": 0.9},
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "config.py", "old": "TIMEOUT = 30", "new": "TIMEOUT = 60"},
            },
            {"action": "final", "summary": "Changed TIMEOUT.", "confidence": 0.9},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "In config.py, change TIMEOUT from 30 to 60.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "completed"
    assert runtime.calls == 4
    forced_schema = runtime.schemas[2]
    assert forced_schema["properties"]["action"]["enum"] == ["tool"]
    assert forced_schema["properties"]["tool"]["enum"] == ["replace_in_file"]
    assert (tmp_path / "config.py").read_text(encoding="utf-8") == "TIMEOUT = 60\n"


def test_forced_tool_recovery_fails_cleanly_if_model_ignores_schema(monkeypatch, tmp_path):
    (tmp_path / "config.py").write_text("TIMEOUT = 30\n", encoding="utf-8")

    runtime = FakeRuntime(
        [
            {"action": "final", "summary": "Changed.", "confidence": 0.9},
            {"action": "final", "summary": "Changed.", "confidence": 0.9},
            {"action": "final", "summary": "Still changed.", "confidence": 0.9},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "In config.py, change TIMEOUT from 30 to 60.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "incomplete"
    assert "edit-tool protocol" in result["summary"]
    assert runtime.calls == 3


def test_noop_write_does_not_count_as_successful_mutation():
    calls = [
        {
            "tool": "write_file",
            "args": {"path": "config.py", "content": "TIMEOUT = 30\n"},
            "result": {"ok": True, "changed": False, "path": "config.py"},
        }
    ]
    assert agent._successful_workspace_mutation(calls) is False


def test_verified_write_counts_as_successful_mutation():
    calls = [
        {
            "tool": "write_file",
            "args": {"path": "config.py", "content": "TIMEOUT = 60\n"},
            "result": {"ok": True, "changed": True, "path": "config.py"},
        }
    ]
    assert agent._successful_workspace_mutation(calls) is True
