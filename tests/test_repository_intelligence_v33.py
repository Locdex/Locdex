from __future__ import annotations

from locdex.intelligence import (
    build_repository_graph,
    find_references,
    find_symbol,
    graph_summary,
    related_files,
)


def _build_fixture(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n\n"
        "def multiply(a, b):\n"
        "    return a * b\n",
        encoding="utf-8",
    )
    (tmp_path / "formatter.py").write_text(
        "from calculator import add, multiply\n\n"
        "def format_sum(a, b):\n"
        "    return f\"sum={add(a, b)}\"\n\n"
        "def format_product(a, b):\n"
        "    return f\"product={multiply(a, b)}\"\n",
        encoding="utf-8",
    )
    (tmp_path / "test_operations.py").write_text(
        "from calculator import add, multiply\n"
        "from formatter import format_product\n\n"
        "def test_product():\n"
        "    assert multiply(3, 4) == 12\n"
        "    assert format_product(3, 4) == \"product=12\"\n",
        encoding="utf-8",
    )


def test_graph_links_imports_and_tests(tmp_path):
    _build_fixture(tmp_path)
    graph = build_repository_graph(str(tmp_path))

    edges = {
        (edge["from"], edge["to"], edge["type"])
        for edge in graph["edges"]
    }
    assert ("formatter.py", "calculator.py", "imports") in edges
    assert ("test_operations.py", "calculator.py", "tests") in edges
    assert ("test_operations.py", "formatter.py", "tests") in edges


def test_symbol_and_reference_queries(tmp_path):
    _build_fixture(tmp_path)

    definitions = find_symbol(str(tmp_path), "multiply")
    references = find_references(str(tmp_path), "multiply")

    assert definitions == [
        {
            "path": "calculator.py",
            "module": "calculator",
            "name": "multiply",
            "kind": "function",
            "line": 4,
        }
    ]
    assert {item["path"] for item in references} >= {
        "formatter.py",
        "test_operations.py",
    }
    assert "calculator.py" not in {item["path"] for item in references}


def test_related_files_rank_cross_file_task(tmp_path):
    _build_fixture(tmp_path)

    ranked = related_files(
        str(tmp_path),
        "Add multiply and expose format_product while keeping tests passing",
        limit=5,
    )
    paths = [row["path"] for row in ranked]

    assert "calculator.py" in paths
    assert "formatter.py" in paths
    assert "test_operations.py" in paths

    summary = graph_summary(
        str(tmp_path),
        "Add multiply and expose format_product",
    )
    assert "calculator.py" in summary
    assert "formatter.py" in summary
    assert "--imports-->" in summary or "--tests-->" in summary
