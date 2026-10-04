from __future__ import annotations

from locdex.agent.engine import AgentEngine as BaseAgentEngine
from locdex.agent.hardened import AgentEngine as HardenedAgentEngine
from locdex.context_manager import ContextManagerConfig, maybe_compact
from locdex.task_state import TaskState


def test_compaction_keeps_state_and_drops_old_file_output():
    state = TaskState.from_task("Fix the payment retry bug.")
    state.pin_file("payments/service.py")
    state.mark_modified("payments/service.py")
    state.record_failure("FAILED tests/test_payments.py::test_retry")

    messages = [
        {"role": "system", "content": "SYSTEM RULES"},
        {"role": "user", "content": "Fix the payment retry bug."},
        {
            "role": "user",
            "content": "TOOL RESULT for read_file:\nOLD_SOURCE_SENTINEL\n" + ("x" * 3000),
        },
        {"role": "assistant", "content": '{"action":"tool","tool":"run_tests","args":{}}'},
        {"role": "user", "content": "LATEST_WORK_SENTINEL"},
    ]

    result = maybe_compact(
        messages,
        state,
        ContextManagerConfig(
            context_window_tokens=1000,
            reserve_output_tokens=150,
            reserve_state_tokens=150,
            trigger_ratio=0.5,
            keep_recent_messages=2,
        ),
    )

    combined = "\n".join(message["content"] for message in result.messages)

    assert result.compacted is True
    assert result.after_tokens < result.before_tokens
    assert "Fix the payment retry bug." in combined
    assert "payments/service.py" in combined
    assert "FAILED tests/test_payments.py::test_retry" in combined
    assert "OLD_SOURCE_SENTINEL" not in combined
    assert "LATEST_WORK_SENTINEL" in combined
    assert state.compactions == 1


def test_small_context_is_left_unchanged():
    state = TaskState.from_task("Inspect app.")
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "inspect app"},
    ]

    result = maybe_compact(
        messages,
        state,
        ContextManagerConfig(context_window_tokens=8192),
    )

    assert result.compacted is False
    assert result.messages == messages
    assert state.compactions == 0


def test_routing_interface_is_unchanged_by_compaction(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    base = BaseAgentEngine(model_key="smoke").prepare("inspect run", str(tmp_path))
    hardened = HardenedAgentEngine(model_key="smoke").prepare("inspect run", str(tmp_path))

    assert hardened["routing_decision"].model == base["routing_decision"].model
    assert hardened["plan"].route == base["plan"].route


class RecordingSession:
    def __init__(self):
        self.calls: list[list[dict[str, str]]] = []
        self.decisions = [
            {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {
                    "path": "app.py",
                    "old": "return 1",
                    "new": "return 2",
                },
            },
            {
                "action": "tool",
                "tool": "read_file",
                "args": {"path": "app.py", "start_line": 1, "end_line": 40},
            },
            {"action": "final", "summary": "Updated app.", "confidence": 0.9},
        ]

    def json_completion(self, messages, schema, **kwargs):
        self.calls.append([dict(message) for message in messages])
        return self.decisions.pop(0)


def test_agent_can_reread_pinned_file_after_compaction(tmp_path):
    (tmp_path / "app.py").write_text(
        "def value():\n    return 1\n",
        encoding="utf-8",
    )

    session = RecordingSession()
    engine = HardenedAgentEngine(model_key="smoke")
    engine.context_manager_config = ContextManagerConfig(
        context_window_tokens=900,
        reserve_output_tokens=100,
        reserve_state_tokens=100,
        trigger_ratio=0.35,
        keep_recent_messages=1,
    )

    result = engine.execute(
        "Change value() to return 2 and verify the result.",
        str(tmp_path),
        session=session,
        max_steps=5,
    )

    assert result["status"] == "completed"
    assert result["context_compactions"] >= 1
    assert "return 2" in (tmp_path / "app.py").read_text(encoding="utf-8")

    second_prompt = "\n".join(message["content"] for message in session.calls[1])
    assert "app.py" in second_prompt
    assert "Modified files:" in second_prompt
    assert "return 1" not in second_prompt

    third_prompt = "\n".join(message["content"] for message in session.calls[2])
    assert "return 2" in third_prompt
