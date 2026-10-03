from __future__ import annotations

from types import SimpleNamespace

from locdex.agent.hardened import _RepairAwareSession


class FakeInner:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def json_completion(self, messages, schema, **kwargs):
        return self.decisions.pop(0)


def test_repeated_exact_edit_forces_source_refresh():
    decision = {
        "action": "tool",
        "tool": "replace_in_file",
        "args": {
            "path": "app.py",
            "old": "return 1",
            "new": "return 2",
        },
    }
    engine = SimpleNamespace(
        _repair_required=False,
        _repair_deferrals=0,
        _mutations_since_validation=0,
    )
    session = _RepairAwareSession(FakeInner([decision, decision]), engine)

    first = session.json_completion([], {})
    second = session.json_completion([], {})

    assert first["tool"] == "replace_in_file"
    assert second["tool"] == "read_file"
    assert second["args"]["path"] == "app.py"


def test_repair_mode_forces_validation_after_two_mutations():
    engine = SimpleNamespace(
        _repair_required=True,
        _repair_deferrals=0,
        _mutations_since_validation=2,
    )
    session = _RepairAwareSession(FakeInner([]), engine)

    decision = session.json_completion([], {})

    assert decision == {
        "action": "tool",
        "tool": "run_tests",
        "args": {},
        "summary": "Re-run validation after bounded repair edits.",
        "confidence": 1.0,
    }
