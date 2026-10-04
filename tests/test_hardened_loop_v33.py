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


def test_fresh_preloaded_read_is_replanned_within_same_step():
    engine = SimpleNamespace(
        _repair_required=False,
        _repair_deferrals=0,
        _mutations_since_validation=0,
        _preloaded_paths={"calculator.py"},
    )
    session = _RepairAwareSession(
        FakeInner(
            [
                {
                    "action": "tool",
                    "tool": "read_file",
                    "args": {"path": "calculator.py"},
                },
                {
                    "action": "tool",
                    "tool": "insert_after_symbol",
                    "args": {
                        "path": "calculator.py",
                        "anchor": "add",
                        "new_source": "def multiply(a, b):\n    return a * b",
                    },
                },
            ]
        ),
        engine,
    )

    decision = session.json_completion([], {})

    assert decision["tool"] == "insert_after_symbol"
    assert decision["args"]["anchor"] == "add"


def test_repeated_failed_literal_edit_is_replanned_to_symbol_edit():
    engine = SimpleNamespace(
        _repair_required=False,
        _repair_deferrals=0,
        _mutations_since_validation=0,
        _preloaded_paths=set(),
    )
    repeated = {
        "action": "tool",
        "tool": "replace_in_file",
        "args": {
            "path": "calculator.py",
            "old": "missing exact text",
            "new": "def multiply(a, b):\n    return a * b",
        },
    }
    session = _RepairAwareSession(
        FakeInner(
            [
                repeated,
                repeated,
                {
                    "action": "tool",
                    "tool": "insert_after_symbol",
                    "args": {
                        "path": "calculator.py",
                        "anchor": "add",
                        "new_source": "def multiply(a, b):\n    return a * b",
                    },
                },
            ]
        ),
        engine,
    )

    first = session.json_completion([], {})
    second = session.json_completion([], {})

    assert first["tool"] == "replace_in_file"
    assert second["tool"] == "insert_after_symbol"
