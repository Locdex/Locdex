from __future__ import annotations

from pathlib import Path

import pytest

from locdex.agent import AgentEngine
from locdex.tools import ToolError, execute_tool


class FakeSession:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def json_completion(self, messages, schema, **kwargs):
        assert schema["properties"]["action"]["enum"] == ["tool", "final", "escalate"]
        if not self.decisions:
            raise AssertionError("Fake session ran out of decisions")
        return self.decisions.pop(0)


def test_agent_executes_read_edit_verify_finish(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    session = FakeSession(
        [
            {"action": "tool", "tool": "read_file", "args": {"path": "app.py"}},
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "app.py", "old": "VALUE = 1", "new": "VALUE = 2"},
            },
            {"action": "final", "summary": "Updated VALUE.", "confidence": 0.9},
        ]
    )

    result = AgentEngine(model_key="smoke").execute(
        "Update VALUE from 1 to 2",
        str(tmp_path),
        session=session,
        max_steps=5,
    )

    assert result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert result["files_modified"] == ["app.py"]
    assert any(call["tool"] == "run_tests" for call in result["tool_calls"])


def test_agent_rejects_premature_final_for_change_task(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    session = FakeSession(
        [
            {"action": "final", "summary": "Done.", "confidence": 0.5},
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "app.py", "old": "x = 1", "new": "x = 2"},
            },
            {"action": "final", "summary": "Changed x.", "confidence": 0.8},
        ]
    )

    result = AgentEngine(model_key="smoke").execute(
        "Change x to 2",
        str(tmp_path),
        session=session,
        max_steps=5,
    )
    assert result["status"] == "completed"
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "x = 2\n"


def test_workspace_path_traversal_is_blocked(tmp_path):
    with pytest.raises(ToolError, match="outside the workspace"):
        execute_tool(
            str(tmp_path),
            "write_file",
            {"path": "../escape.txt", "content": "no"},
        )


def test_generic_command_cannot_bypass_git_tools(tmp_path):
    with pytest.raises(ToolError, match="dedicated Git tools"):
        execute_tool(
            str(tmp_path),
            "run_command",
            {"argv": ["git", "status"]},
        )


def test_git_mutation_requires_explicit_intent(tmp_path):
    with pytest.raises(ToolError, match="explicit user intent"):
        execute_tool(
            str(tmp_path),
            "git_commit",
            {"message": "should not run"},
            explicit_user_intent=False,
        )
