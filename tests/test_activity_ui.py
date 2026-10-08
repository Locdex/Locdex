from __future__ import annotations

from locdex.cli.activity import ActivityState, describe_tool
from locdex.events import AgentEvent


def test_activity_tracks_actual_tools_without_rendering_file_body():
    state = ActivityState()
    assert "Preparing" in state.toolbar(frame=0)
    assert state.on_progress("[Agent] Step 2/12: choosing next action...")
    assert state.step == 2
    assert state.max_steps == 12
    requested = state.on_event(
        AgentEvent(
            "tool.requested",
            {
                "tool": "replace_in_file",
                "args": {
                    "path": "src/calculator.py",
                    "content": "secret code never render",
                },
            },
        )
    )
    assert "Editing: src/calculator.py" in requested
    assert "secret code" not in requested
    assert "2/12" in state.toolbar(frame=3)
    assert "0 tools" in state.toolbar(frame=3)
    finished = state.on_event(
        AgentEvent("tool.completed", {"tool": "replace_in_file", "result": {"ok": True}})
    )
    assert "✓" in finished
    assert state.tools_completed == 1
    assert "1 tools" in state.toolbar(frame=4)


def test_activity_shows_failures_and_verification():
    state = ActivityState()
    line = state.on_event(
        AgentEvent("tool.completed", {"tool": "run_tests", "result": {"error": "failed"}})
    )
    assert line.startswith("✗")
    assert state.on_progress("[Agent] verify") == "Verifying changes"
    assert "Verifying changes" in state.toolbar(frame=2)


def test_activity_does_not_print_arbitrary_commands_or_patches():
    assert describe_tool(
        "run_command",
        {"argv": ["python", "-c", "print('secret code')"]},
    ) == "Running python"
    assert "return secret" not in describe_tool("write_file", {"content": "return secret", "path": "a.py"})
