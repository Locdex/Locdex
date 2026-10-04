from __future__ import annotations

from locdex.task_state import TaskState


def test_task_state_preserves_objective_files_and_failure_metadata():
    state = TaskState.from_task(
        "Implement context compaction.",
        ["Agent continues correctly after old context is discarded."],
    )
    state.pin_file("src/locdex/agent.py")
    state.mark_modified("src/locdex/context_manager.py")
    state.record_failure("FAILED tests/test_context.py::test_compaction")
    state.set_next_action("repair task-state update")

    prompt = state.to_prompt()

    assert "Implement context compaction." in prompt
    assert "src/locdex/agent.py" in prompt
    assert "src/locdex/context_manager.py" in prompt
    assert "FAILED tests/test_context.py::test_compaction" in prompt
    assert "repair task-state update" in prompt


def test_new_edit_marks_previous_validation_stale():
    state = TaskState.from_task("Fix router.")
    state.mark_validation(True)

    assert state.last_validation_status == "passed"
    assert state.validation_stale is False

    state.mark_modified("src/locdex/router.py")

    assert state.validation_stale is True
    assert state.next_action == "validate modified workspace"


def test_passing_validation_clears_old_failures():
    state = TaskState.from_task("Fix tests.")
    state.record_failure("FAILED test_router.py::test_fallback")

    state.mark_validation(True)

    assert state.failing_checks == []
    assert state.last_validation_status == "passed"
    assert state.validation_stale is False


def test_secrets_never_enter_task_state():
    state = TaskState.from_task(
        "Fix auth with password=hunter2",
        ["Keep api_key=supersecret working"],
    )
    state.add_decision("token=abc123 should remain local")
    state.record_failure("secret=myvalue was rejected")

    prompt = state.to_prompt()

    assert "hunter2" not in prompt
    assert "supersecret" not in prompt
    assert "abc123" not in prompt
    assert "myvalue" not in prompt
    assert "REDACTED_SECRET" in prompt
