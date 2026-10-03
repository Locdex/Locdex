from __future__ import annotations

from locdex.agent.guards import (
    clean_model_result,
    guard_mutation_result,
    preexisting_changed_paths,
    snapshot_file,
)


def test_read_source_prefixes_are_removed_for_model():
    result = clean_model_result(
        "read_file",
        {"content": "1: from calculator import add\n2: \n3: def run():\n4:     return 1"},
    )
    assert result["content"] == "from calculator import add\n\ndef run():\n    return 1"


def test_invalid_python_mutation_is_rolled_back(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    args = {"path": "app.py"}
    snapshot = snapshot_file(str(tmp_path), "replace_in_file", args, {"replace_in_file"})
    target.write_text("def value() * 2:\n    return 1\n", encoding="utf-8")

    result = guard_mutation_result(
        str(tmp_path),
        "replace_in_file",
        args,
        {"ok": True, "path": "app.py"},
        snapshot,
    )

    assert result["rolled_back"] is True
    assert target.read_text(encoding="utf-8") == "def value():\n    return 1\n"


def test_cache_paths_not_reported_as_user_changes():
    result = preexisting_changed_paths(
        {
            "ok": True,
            "output": "## main\n?? __pycache__/\n?? calculator.py\n M formatter.py\n",
        }
    )
    assert result == {"calculator.py", "formatter.py"}
