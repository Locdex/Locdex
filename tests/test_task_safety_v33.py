from __future__ import annotations

from locdex.agent import AgentEngine
from locdex.agent.change_journal import ChangeJournal
from locdex.intelligence import plan_retrieval
from locdex.task_state import TaskState


class FakeSession:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def json_completion(self, messages, schema, **kwargs):
        if not self.decisions:
            raise AssertionError("Fake session ran out of decisions")
        return self.decisions.pop(0)


def test_incomplete_or_escalated_task_restores_original_file(tmp_path):
    target = tmp_path / "app.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")

    session = FakeSession(
        [
            {
                "action": "tool",
                "tool": "replace_symbol",
                "args": {
                    "path": "app.py",
                    "name": "value",
                    "new_source": "def value():\n    return 2",
                },
            },
            {
                "action": "escalate",
                "reason": "fixture stops after one edit",
                "confidence": 0.1,
            },
        ]
    )

    result = AgentEngine(model_key="smoke").execute(
        "Change value in app.py to return 2.",
        str(tmp_path),
        session=session,
        max_steps=3,
    )

    assert result["status"] == "escalate"
    assert result["rollback_performed"] is True
    assert result["rolled_back_files"] == ["app.py"]
    assert result["attempted_files_modified"] == ["app.py"]
    assert result["files_modified"] == []
    assert target.read_text(encoding="utf-8") == original


def _prepared_engine(tmp_path, task: str) -> AgentEngine:
    engine = AgentEngine(model_key="smoke")
    engine.task_state = TaskState.from_task(task)
    engine.retrieval_plan = plan_retrieval(str(tmp_path), task)
    engine.change_journal = ChangeJournal(str(tmp_path))
    return engine


def test_test_file_mutation_is_blocked_when_user_only_says_make_tests_pass(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_calculator.py"
    original = (
        "from calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    )
    test_file.write_text(original, encoding="utf-8")

    task = "Fix calculator.py so the tests pass."
    engine = _prepared_engine(tmp_path, task)
    result = engine._run_tool(
        repo_path=str(tmp_path),
        task=task,
        name="replace_in_file",
        args={
            "path": "test_calculator.py",
            "old": "assert add(2, 3) == 5",
            "new": "assert add(2, 3) == -1",
        },
        progress=None,
    )

    assert result["change_surface_blocked"] is True
    assert "tests are verification evidence" in result["error"]
    assert test_file.read_text(encoding="utf-8") == original


def test_explicit_test_update_is_allowed(tmp_path):
    test_file = tmp_path / "test_app.py"
    test_file.write_text(
        "def test_value():\n    assert 1 == 1\n",
        encoding="utf-8",
    )

    task = "Update test_app.py to assert 2 == 2."
    engine = _prepared_engine(tmp_path, task)
    result = engine._run_tool(
        repo_path=str(tmp_path),
        task=task,
        name="replace_in_file",
        args={
            "path": "test_app.py",
            "old": "assert 1 == 1",
            "new": "assert 2 == 2",
        },
        progress=None,
    )

    assert result["ok"] is True
    assert "assert 2 == 2" in test_file.read_text(encoding="utf-8")


def test_existing_file_outside_change_surface_is_blocked(tmp_path):
    app = tmp_path / "app.py"
    other = tmp_path / "other.py"
    app.write_text("VALUE = 1\n", encoding="utf-8")
    other.write_text("OTHER = 1\n", encoding="utf-8")

    task = "Change VALUE in app.py from 1 to 2."
    engine = _prepared_engine(tmp_path, task)
    result = engine._run_tool(
        repo_path=str(tmp_path),
        task=task,
        name="replace_in_file",
        args={
            "path": "other.py",
            "old": "OTHER = 1",
            "new": "OTHER = 2",
        },
        progress=None,
    )

    assert result["change_surface_blocked"] is True
    assert other.read_text(encoding="utf-8") == "OTHER = 1\n"
