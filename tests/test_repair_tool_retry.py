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


def _config(steps=10):
    return SimpleNamespace(max_agent_steps=steps, model_key="smoke")


def test_failed_repair_tool_gets_fresh_readback_and_retry(monkeypatch, tmp_path):
    state = {
        "content": "def is_even(n):\\n    pass\\n",
        "tests": 0,
        "reads": 0,
    }

    def fake_execute(repo_path, name, args):
        del repo_path

        if name == "list_files":
            return {"files": ["helpers.py", "test_helpers.py"], "truncated": False}

        if name == "read_file":
            state["reads"] += 1
            if args["path"] == "helpers.py":
                return {"path": "helpers.py", "content": state["content"]}
            return {
                "path": "test_helpers.py",
                "content": (
                    "assert is_even(4) is True\\n"
                    "assert is_even(5) is False"
                ),
            }

        if name == "run_tests":
            state["tests"] += 1
            ok = "return n % 2 == 0" in state["content"]
            return {
                "ok": ok,
                "returncode": 0 if ok else 1,
                "output": "2 passed" if ok else "2 failed",
            }

        if name == "replace_in_file":
            old = str(args["old"])
            new = str(args["new"])

            if old == new:
                raise agent.ToolError(
                    "replace_in_file old and new text are identical; this would not change the file."
                )

            if old not in state["content"]:
                raise agent.ToolError("Exact text to replace was not found.")

            state["content"] = state["content"].replace(old, new, 1)
            return {
                "ok": True,
                "changed": True,
                "path": "helpers.py",
                "replacements": 1,
            }

        raise AssertionError(name)

    runtime = FakeRuntime(
        [
            # First edit is real but wrong.
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {
                    "path": "helpers.py",
                    "old": "pass",
                    "new": "return n % 2 != 0",
                },
            },
            # Validation repair attempt is malformed/no-op.
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {
                    "path": "helpers.py",
                    "old": "return n % 2 != 0",
                    "new": "return n % 2 != 0",
                },
            },
            # Tool-recovery retry repairs the actual current file.
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {
                    "path": "helpers.py",
                    "old": "return n % 2 != 0",
                    "new": "return n % 2 == 0",
                },
            },
            {
                "action": "final",
                "summary": "Implemented is_even and tests pass.",
                "confidence": 0.9,
            },
        ]
    )

    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Implement is_even(n) in helpers.py so the existing tests pass. Run the tests.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "completed"
    assert runtime.calls == 4
    assert "return n % 2 == 0" in state["content"]
    # bootstrap fail + post-first-edit fail + post-repair pass
    assert state["tests"] == 3
    # Includes bootstrap reads, successful mutation readbacks, and failed-edit refresh.
    assert state["reads"] >= 5


def test_repeated_failed_edit_tools_stop_bounded(monkeypatch, tmp_path):
    def fake_execute(repo_path, name, args):
        del repo_path
        if name == "list_files":
            return {"files": ["helpers.py"], "truncated": False}
        if name == "read_file":
            return {"path": "helpers.py", "content": "def is_even(n):\\n    pass"}
        if name == "replace_in_file":
            raise agent.ToolError("Exact text to replace was not found.")
        return {"ok": False, "returncode": None, "output": "No tests"}

    runtime = FakeRuntime(
        [
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "helpers.py", "old": "x", "new": "y"},
            },
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "helpers.py", "old": "x", "new": "z"},
            },
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "helpers.py", "old": "x", "new": "q"},
            },
        ]
    )

    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "Implement is_even in helpers.py.",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "incomplete"
    assert "edit-tool recovery attempts" in result["summary"]
    assert runtime.calls == 3
