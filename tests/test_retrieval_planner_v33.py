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
