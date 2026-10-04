from __future__ import annotations

from locdex.intelligence import (
    build_repository_graph,
    detect_missing_local_imports,
    plan_retrieval,
)


def _broken_fixture(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "formatter.py").write_text(
        "from calculator import add\n\n"
        "def format_product(a, b):\n"
        "    return f\"product={add(a, b) * 2}\"\n",
        encoding="utf-8",
    )
    (tmp_path / "test_operations.py").write_text(
        "from calculator import add, multiply\n"
        "from formatter import format_sum, format_product\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n\n"
        "def test_multiply():\n"
        "    assert multiply(3, 4) == 12\n\n"
        "def test_format_sum():\n"
        "    assert format_sum(2, 3) == \"sum=5\"\n\n"
        "def test_format_product():\n"
        "    assert format_product(3, 4) == \"product=12\"\n",
        encoding="utf-8",
    )


def test_graph_preserves_imported_symbol_names(tmp_path):
    _broken_fixture(tmp_path)

    graph = build_repository_graph(str(tmp_path))
    tests = next(row for row in graph["files"] if row["path"] == "test_operations.py")

    calculator_import = next(
        row for row in tests["imports"] if row["module"] == "calculator"
    )
    formatter_import = next(
        row for row in tests["imports"] if row["module"] == "formatter"
    )

    assert [item["name"] for item in calculator_import["names"]] == ["add", "multiply"]
    assert [item["name"] for item in formatter_import["names"]] == [
        "format_sum",
        "format_product",
    ]


def test_detects_missing_symbols_required_by_local_tests(tmp_path):
    _broken_fixture(tmp_path)

    missing = detect_missing_local_imports(str(tmp_path))
    pairs = {(item.name, item.target_path, item.requested_by) for item in missing}

    assert ("multiply", "calculator.py", "test_operations.py") in pairs
    assert ("format_sum", "formatter.py", "test_operations.py") in pairs
    assert not any(item.name == "add" for item in missing)
    assert not any(item.name == "format_product" for item in missing)
    assert all(item.requested_by_test for item in missing)


def test_retrieval_plan_turns_structural_gaps_into_change_surface(tmp_path):
    _broken_fixture(tmp_path)

    plan = plan_retrieval(
        str(tmp_path),
        "Add multiply to calculator and expose format_product through formatter while keeping tests passing",
        max_files=8,
        source_tokens=1200,
    )

    missing = {(item.name, item.target_path) for item in plan.missing_symbols}

    assert ("multiply", "calculator.py") in missing
    assert ("format_sum", "formatter.py") in missing
    assert {"calculator.py", "formatter.py"} <= set(plan.likely_change_files)
    assert "test_operations.py" in plan.related_tests
    assert {"multiply", "format_sum", "format_product"} <= set(plan.required_symbols)
    assert any(row["reason"] == "reference:multiply" for row in plan.exact_ranges)
    assert any("multiply is imported" in finding for finding in plan.findings)
    assert [action["tool"] for action in plan.initial_actions] == [
        "get_reference_context",
        "get_reference_context",
        "read_file",
        "read_file",
    ]
    assert plan.initial_actions[0]["args"]["name"] == "multiply"
    assert plan.initial_actions[1]["args"]["name"] == "format_sum"
    assert plan.initial_actions[2]["args"]["path"] == "calculator.py"
    assert plan.initial_actions[3]["args"]["path"] == "formatter.py"


def test_constants_aliases_and_reexports_are_valid_bindings(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from .values import LIMIT\n",
        encoding="utf-8",
    )
    (package / "values.py").write_text(
        "LIMIT = 5\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        "from pkg import LIMIT as MAX_LIMIT\n"
        "from pkg.values import LIMIT\n",
        encoding="utf-8",
    )

    missing = detect_missing_local_imports(str(tmp_path))

    assert missing == []


def test_local_submodule_import_is_not_reported_missing(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text(
        "def run():\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        "from pkg import helpers\n",
        encoding="utf-8",
    )

    missing = detect_missing_local_imports(str(tmp_path))

    assert missing == []


def test_hardened_engine_seeds_task_state_before_first_model_turn(tmp_path):
    from locdex.agent.hardened import AgentEngine

    _broken_fixture(tmp_path)
    engine = AgentEngine(model_key="smoke")

    class InspectingSession:
        def __init__(self):
            self.seen = False

        def json_completion(self, messages, schema, **kwargs):
            self.seen = True
            decisions = "\n".join(engine.task_state.decisions)
            assert "missing local symbol multiply expected in calculator.py" in decisions
            assert "missing local symbol format_sum expected in formatter.py" in decisions
            assert {"calculator.py", "formatter.py", "test_operations.py"} <= set(
                engine.task_state.pinned_files
            )
            assert engine.task_state.next_action is not None
            return {
                "action": "final",
                "summary": "Inspected retrieval plan.",
                "confidence": 0.9,
            }

    session = InspectingSession()
    result = engine.execute(
        "Inspect multiply and format_sum dependencies.",
        str(tmp_path),
        session=session,
        max_steps=2,
    )

    assert session.seen is True
    assert result["status"] == "completed"
    missing = {
        (item["name"], item["target_path"])
        for item in result["retrieval_plan"]["missing_symbols"]
    }
    assert ("multiply", "calculator.py") in missing
    assert ("format_sum", "formatter.py") in missing


def test_retrieval_plan_executes_before_first_model_decision(tmp_path):
    from locdex.agent.hardened import AgentEngine

    _broken_fixture(tmp_path)
    engine = AgentEngine(model_key="smoke")

    class RecordingSession:
        def __init__(self):
            self.calls = []

        def json_completion(self, messages, schema, **kwargs):
            self.calls.append([dict(message) for message in messages])
            return {
                "action": "final",
                "summary": "Inspected deterministic retrieval.",
                "confidence": 0.9,
            }

    session = RecordingSession()
    result = engine.execute(
        "Inspect multiply and format_sum dependencies.",
        str(tmp_path),
        session=session,
        max_steps=2,
    )

    assert result["status"] == "completed"
    assert result["steps"] == 1
    assert len(session.calls) == 1

    first_prompt = "\n".join(message["content"] for message in session.calls[0])
    assert "DETERMINISTIC RETRIEVAL RESULT for get_reference_context" in first_prompt
    assert "assert multiply(3, 4) == 12" in first_prompt
    assert "assert format_sum(2, 3) == \"sum=5\"" in first_prompt
    assert "DETERMINISTIC RETRIEVAL RESULT for read_file" in first_prompt
    assert "def add(a, b):" in first_prompt
    assert "def format_product(a, b):" in first_prompt

    deterministic = [
        call for call in result["tool_calls"]
        if call.get("deterministic_retrieval") is True
    ]
    assert [call["tool"] for call in deterministic] == [
        "get_reference_context",
        "get_reference_context",
        "read_file",
        "read_file",
    ]

    reads = [
        call["args"]["path"]
        for call in result["tool_calls"]
        if call["tool"] == "read_file"
    ]
    assert reads.count("calculator.py") == 1
    assert reads.count("formatter.py") == 1


def test_retrieval_prelude_for_change_task_preserves_model_step_budget(tmp_path):
    from locdex.agent.hardened import AgentEngine

    _broken_fixture(tmp_path)
    engine = AgentEngine(model_key="smoke")

    class OneStepEditSession:
        def __init__(self):
            self.calls = 0

        def json_completion(self, messages, schema, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "action": "tool",
                    "tool": "replace_in_file",
                    "args": {
                        "path": "calculator.py",
                        "old": "def add(a, b):\n    return a + b",
                        "new": (
                            "def add(a, b):\n"
                            "    return a + b\n\n"
                            "def multiply(a, b):\n"
                            "    return a * b"
                        ),
                    },
                }
            return {
                "action": "escalate",
                "reason": "fixture stops after proving the first edit turn",
                "confidence": 0.1,
            }

    session = OneStepEditSession()
    result = engine.execute(
        "Add multiply to calculator and expose format_product through formatter while keeping tests passing.",
        str(tmp_path),
        session=session,
        max_steps=2,
    )

    assert "def multiply(a, b):" in (tmp_path / "calculator.py").read_text(encoding="utf-8")
    assert result["steps"] <= 2
    deterministic = [
        call for call in result["tool_calls"]
        if call.get("deterministic_retrieval") is True
    ]
    assert len(deterministic) == 4
    assert session.calls >= 1
