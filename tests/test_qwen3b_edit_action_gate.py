"""Require an actual edit action before a small local coding model can finish."""
from __future__ import annotations

from locdex.agent import AgentEngine
from locdex.agent.protocol import system_prompt


class FakeQwen3B:
    def __init__(self):
        self.actions = []
        self.schemas = []

    def json_completion(self, messages, schema, **kwargs):
        allowed = schema["properties"]["action"]["enum"]
        self.schemas.append(list(allowed))
        if not self.actions:
            assert allowed == ["tool", "escalate"]
            self.actions.append("edit")
            return {
                "action": "tool",
                "tool": "replace_in_file",
                "args": {"path": "calculator.py", "old": "return a - b", "new": "return a + b"},
            }
        assert "final" in allowed
        self.actions.append("final")
        return {"action": "final", "summary": "Corrected arithmetic.", "confidence": 0.8}


class EscalatingQwen3B:
    def __init__(self):
        self.calls = 0

    def json_completion(self, messages, schema, **kwargs):
        self.calls += 1
        assert "final" not in schema["properties"]["action"]["enum"]
        return {
            "action": "escalate",
            "reason": "Cannot produce a safe edit.",
            "confidence": 0.1,
        }


def test_qwen3b_prompt_examples_explain_write_before_final():
    text = system_prompt("", "qwen25-3b")
    assert "COMPACT LOCAL MODEL GUIDANCE" in text
    assert '"tool":"replace_in_file"' in text
    assert "Do not merely describe a patch" in text


def test_qwen3b_small_change_has_edit_only_gate_then_final(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8"
    )
    fake = FakeQwen3B()
    events = []
    result = AgentEngine(model_key="qwen25-3b").execute(
        "Fix calculator.py add so it adds rather than subtracts.",
        str(tmp_path),
        session=fake,
        progress=events.append,
        max_steps=4,
    )
    assert result["status"] == "completed"
    assert result["files_modified"] == ["calculator.py"]
    assert result["verification"]["passed"] is True
    assert fake.schemas[0] == ["tool", "escalate"]
    assert fake.schemas[-1] == ["tool", "final", "escalate"]
    assert any("requested replace_in_file" in text for text in events)
    assert (tmp_path / "calculator.py").read_text(encoding="utf-8").endswith("return a + b\n")


def test_qwen3b_escalation_without_edits_never_claims_success(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8"
    )
    fake = EscalatingQwen3B()
    result = AgentEngine(model_key="qwen25-3b").execute(
        "Fix calculator.py add to return the sum.",
        str(tmp_path),
        session=fake,
        max_steps=3,
    )
    assert result["status"] != "completed"
    assert result["files_modified"] == []
    assert (tmp_path / "calculator.py").read_text(encoding="utf-8").endswith("return a - b\n")
