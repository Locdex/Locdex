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


def _config(steps=8):
    return SimpleNamespace(max_agent_steps=steps, model_key="smoke")


def test_smoke_auto_validates_after_verified_edit(monkeypatch, tmp_path):
    state = {"content": "def is_even(n):\\n    pass\\n", "tests": 0}

    def fake_execute(repo_path, name, args):
        del repo_path
        if name == "list_files":
            return {"files": ["helpers.py", "test_helpers.py"], "truncated": False}
        if name == "read_file":
            if args["path"] == "helpers.py":
                return {"path": "helpers.py", "content": state["content"]}
            return {"path": "test_helpers.py", "content": "tests"}
        if name == "replace_in_file":
            state["content"] = "def is_even(n):\\n    return n % 2 == 0\\n"
            return {"ok": True, "changed": True, "path": "helpers.py", "replacements": 1}
        if name == "run_tests":
            state["tests"] += 1
            ok = "n % 2 == 0" in state["content"]
            return {
                "ok": ok,
                "returncode": 0 if ok else 1,
                "output": "2 passed" if ok else "2 failed",
            }
        raise AssertionError(name)

    runtime = FakeRuntime(
        [
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "helpers.py", "old": "pass", "new": "return n % 2 == 0"},
            },
            {"action": "final", "summary": "Implemented is_even and tests pass.", "confidence": 0.9},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Implement is_even(n) in helpers.py so the tests pass. Run the tests.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "completed"
    # bootstrap validation + automatic post-edit validation
    assert state["tests"] == 2
    assert runtime.calls == 2


def test_failed_smoke_validation_forces_repair_instead_of_spinning(monkeypatch, tmp_path):
    state = {"content": "def is_even(n):\\n    pass\\n", "tests": 0}

    def fake_execute(repo_path, name, args):
        del repo_path
        if name == "list_files":
            return {"files": ["helpers.py", "test_helpers.py"], "truncated": False}
        if name == "read_file":
            return {"path": args["path"], "content": state["content"] if args["path"] == "helpers.py" else "tests"}
        if name == "replace_in_file":
            new = str(args["new"])
            if "!= 0" in new:
                state["content"] = "def is_even(n):\\n    return n % 2 != 0\\n"
            else:
                state["content"] = "def is_even(n):\\n    return n % 2 == 0\\n"
            return {"ok": True, "changed": True, "path": "helpers.py", "replacements": 1}
        if name == "run_tests":
            state["tests"] += 1
            ok = "n % 2 == 0" in state["content"]
            return {
                "ok": ok,
                "returncode": 0 if ok else 1,
                "output": "2 passed" if ok else "2 failed",
            }
        raise AssertionError(name)

    runtime = FakeRuntime(
        [
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "helpers.py", "old": "pass", "new": "return n % 2 != 0"},
            },
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "helpers.py", "old": "return n % 2 != 0", "new": "return n % 2 == 0"},
            },
            {"action": "final", "summary": "Implemented is_even and tests pass.", "confidence": 0.9},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Implement is_even(n) in helpers.py so the tests pass. Run the tests.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "completed"
    assert runtime.calls == 3
    # second generation was constrained to an edit tool after failed validation
    assert runtime.schemas[1]["properties"]["action"]["enum"] == ["tool"]
    assert "n % 2 == 0" in state["content"]
    assert state["tests"] == 3  # bootstrap + failed post-edit + passing post-repair
