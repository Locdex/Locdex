from __future__ import annotations

from types import SimpleNamespace

from locdex import agent


class FakeRuntime:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def json_completion(self, messages, schema):
        del messages, schema
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return decision


def _config(steps=6, model_key="smoke"):
    return SimpleNamespace(max_agent_steps=steps, model_key=model_key)


def test_small_repo_is_pre_read_before_first_generation(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text("def test_value():\n    assert True\n", encoding="utf-8")

    seen = []

    def fake_execute(repo_path, name, args):
        seen.append(name)
        if name == "list_files":
            return {"files": ["app.py", "test_app.py"], "truncated": False}
        if name == "read_file":
            path = args["path"]
            return {"path": path, "content": (tmp_path / path).read_text(encoding="utf-8")}
        if name == "run_tests":
            return {"ok": True, "returncode": 0, "output": "1 passed"}
        return {"ok": True}

    runtime = FakeRuntime([{"action": "final", "summary": "No change requested."}])
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Inspect the project and run the tests.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert seen[:4] == ["list_files", "read_file", "read_file", "run_tests"]
    assert result["status"] == "completed"


def test_immediate_smoke_escalation_gets_one_retry(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    def fake_execute(repo_path, name, args):
        if name == "list_files":
            return {"files": ["app.py"], "truncated": False}
        if name == "read_file":
            return {"path": "app.py", "content": "1: VALUE = 1"}
        if name == "replace_in_file":
            return {"ok": True, "path": "app.py", "replacements": 1}
        return {"ok": True}

    runtime = FakeRuntime(
        [
            {"action": "escalate", "reason": "too hard"},
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "app.py", "old": "VALUE = 1", "new": "VALUE = 2"},
            },
            {"action": "final", "summary": "Updated app.py", "confidence": 0.8},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Change VALUE to 2.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert runtime.calls == 3
    assert result["status"] == "completed"


def test_large_repo_is_not_eagerly_pre_read(monkeypatch, tmp_path):
    for idx in range(agent.SMALL_REPO_MAX_FILES + 1):
        (tmp_path / f"file_{idx}.py").write_text(f"VALUE = {idx}\n", encoding="utf-8")

    reads = []

    def fake_execute(repo_path, name, args):
        if name == "list_files":
            return {
                "files": [f"file_{idx}.py" for idx in range(agent.SMALL_REPO_MAX_FILES + 1)],
                "truncated": False,
            }
        if name == "read_file":
            reads.append(args["path"])
            return {"path": args["path"], "content": "VALUE = 1"}
        return {"ok": True}

    runtime = FakeRuntime([{"action": "final", "summary": "Inspected."}])
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Inspect this project.",
        repo_path=str(tmp_path),
        config=_config(model_key="qwen"),
    )

    assert reads == []
    assert result["status"] == "completed"
