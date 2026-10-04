from __future__ import annotations

from locdex.context import ContextBudget, ContextCompiler
from locdex.intelligence import (
    build_task_context,
    get_reference_context,
    get_symbol_source,
)


def _fixture(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "formatter.py").write_text(
        "from calculator import add\n\n"
        "def format_product(a, b):\n"
        "    return f\"product={add(a, b)}\"\n",
        encoding="utf-8",
    )
    (tmp_path / "test_operations.py").write_text(
        "from calculator import add, multiply\n"
        "from formatter import format_product\n\n"
        "def test_multiply():\n"
        "    assert multiply(3, 4) == 12\n\n"
        "def test_format_product():\n"
        "    assert format_product(3, 4) == \"product=12\"\n",
        encoding="utf-8",
    )


def test_get_symbol_source_returns_exact_ast_range(tmp_path):
    _fixture(tmp_path)

    result = get_symbol_source(str(tmp_path), "format_product")

    assert len(result) == 1
    row = result[0]
    assert row["path"] == "formatter.py"
    assert row["start_line"] == 2
    assert row["end_line"] == 4
    assert "def format_product(a, b):" in row["content"]
    assert "return f\"product={add(a, b)}\"" in row["content"]


def test_get_reference_context_returns_small_usage_ranges(tmp_path):
    _fixture(tmp_path)

    refs = get_reference_context(
        str(tmp_path),
        "multiply",
        context_lines=1,
        limit=5,
    )

    assert len(refs) == 1
    assert refs[0]["path"] == "test_operations.py"
    assert refs[0]["is_test"] is True
    assert "assert multiply(3, 4) == 12" in refs[0]["content"]
    assert refs[0]["end_line"] - refs[0]["start_line"] <= 2


def test_task_context_includes_existing_definition_and_missing_symbol_evidence(tmp_path):
    _fixture(tmp_path)

    pack = build_task_context(
        str(tmp_path),
        "Add multiply and expose format_product while keeping tests passing",
        max_tokens=900,
        max_files=5,
    )

    combined = "\n".join(item["content"] for item in pack["snippets"])

    assert "def format_product(a, b):" in combined
    assert "multiply(3, 4)" in combined
    assert any(item["path"] == "calculator.py" for item in pack["snippets"])
    assert pack["tokens"] <= pack["budget"]


def test_compiler_prioritizes_graph_and_exact_source_before_repo_map(tmp_path):
    _fixture(tmp_path)

    pack = ContextCompiler().compile(
        str(tmp_path),
        "Add multiply and expose format_product while keeping tests passing",
        ContextBudget(max_input_tokens=1800),
    )

    labels = [item.label for item in pack.items]

    assert labels[0] == "task"
    assert "repo_graph" in labels
    assert "task_source" in labels
    assert labels.index("repo_graph") < labels.index("repo_map")
    assert labels.index("task_source") < labels.index("repo_map")
    assert pack.total_tokens <= 1800
