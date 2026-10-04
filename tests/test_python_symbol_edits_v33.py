from __future__ import annotations

import pytest

from locdex.tools import ToolError, execute_tool


def test_insert_after_symbol_adds_new_function(tmp_path):
    target = tmp_path / "calculator.py"
    target.write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    result = execute_tool(
        str(tmp_path),
        "insert_after_symbol",
        {
            "path": "calculator.py",
            "anchor": "add",
            "new_source": "def multiply(a, b):\n    return a * b",
        },
    )

    assert result["ok"] is True
    assert result["operation"] == "insert_after_symbol"
    text = target.read_text(encoding="utf-8")
    assert "def add(a, b):" in text
    assert "def multiply(a, b):" in text
    assert "return a * b" in text
    compile(text, str(target), "exec")


def test_replace_symbol_replaces_only_named_function(tmp_path):
    target = tmp_path / "formatter.py"
    target.write_text(
        "from calculator import add, multiply\n\n"
        "def format_sum(a, b):\n"
        "    return f\"sum={add(a, b)}\"\n\n"
        "def format_product(a, b):\n"
        "    return f\"product={add(a, b) * 2}\"\n",
        encoding="utf-8",
    )

    result = execute_tool(
        str(tmp_path),
        "replace_symbol",
        {
            "path": "formatter.py",
            "name": "format_product",
            "new_source": (
                "def format_product(a, b):\n"
                "    return f\"product={multiply(a, b)}\""
            ),
        },
    )

    assert result["ok"] is True
    text = target.read_text(encoding="utf-8")
    assert 'return f"sum={add(a, b)}"' in text
    assert 'return f"product={multiply(a, b)}"' in text
    assert "add(a, b) * 2" not in text
    compile(text, str(target), "exec")


def test_invalid_symbol_edit_is_rejected_without_changing_file(tmp_path):
    target = tmp_path / "app.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")

    with pytest.raises(ToolError, match="invalid Python symbol edit"):
        execute_tool(
            str(tmp_path),
            "replace_symbol",
            {
                "path": "app.py",
                "name": "value",
                "new_source": "def value() * 2:\n    return 2",
            },
        )

    assert target.read_text(encoding="utf-8") == original


def test_symbol_edit_path_traversal_is_blocked(tmp_path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def value():\n    return 1\n", encoding="utf-8")

    with pytest.raises(ToolError, match="outside the workspace"):
        execute_tool(
            str(tmp_path),
            "replace_symbol",
            {
                "path": "../outside.py",
                "name": "value",
                "new_source": "def value():\n    return 2",
            },
        )
