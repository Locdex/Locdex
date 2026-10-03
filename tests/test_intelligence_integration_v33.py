from __future__ import annotations

from locdex.agent.hardened import AgentEngine
from locdex.context import ContextBudget, ContextCompiler


def test_context_pack_contains_task_ranked_repo_graph(tmp_path):
    (tmp_path / "service.py").write_text(
        "def charge():\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "test_service.py").write_text(
        "from service import charge\n\ndef test_charge():\n    assert charge()\n",
        encoding="utf-8",
    )

    pack = ContextCompiler().compile(
        str(tmp_path),
        "fix charge tests",
        ContextBudget(max_input_tokens=1200),
    )

    labels = {item.label for item in pack.items}
    assert "repo_graph" in labels
    graph_text = next(item.content for item in pack.items if item.label == "repo_graph")
    assert "service.py" in graph_text
    assert "test_service.py" in graph_text


def test_hardened_agent_exposes_read_only_intelligence_tools(tmp_path):
    (tmp_path / "maths.py").write_text(
        "def multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_maths.py").write_text(
        "from maths import multiply\n\ndef test_multiply():\n    assert multiply(2, 3) == 6\n",
        encoding="utf-8",
    )

    engine = AgentEngine(model_key="smoke")

    symbol = engine._run_tool(
        repo_path=str(tmp_path),
        task="inspect multiply",
        name="find_symbol",
        args={"name": "multiply"},
        progress=None,
    )
    refs = engine._run_tool(
        repo_path=str(tmp_path),
        task="inspect multiply",
        name="find_references",
        args={"name": "multiply"},
        progress=None,
    )
    related = engine._run_tool(
        repo_path=str(tmp_path),
        task="fix multiply tests",
        name="related_files",
        args={"limit": 5},
        progress=None,
    )

    assert symbol["matches"][0]["path"] == "maths.py"
    assert {item["path"] for item in refs["matches"]} == {"test_maths.py"}
    assert {item["path"] for item in related["files"]} >= {"maths.py", "test_maths.py"}
