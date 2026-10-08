from __future__ import annotations

from locdex.cli.interactive import _InterruptState, _is_exit_command


def test_exact_exit_commands_close_chat():
    for command in ("exit", "QUIT", " /exit ", "/quit", ":q"):
        assert _is_exit_command(command)


def test_exit_word_inside_a_real_task_does_not_close_chat():
    for instruction in (
        "exit the loop in calculator.py",
        "Please explain the exit condition",
        "quit() returns from the function",
        "/help",
    ):
        assert not _is_exit_command(instruction)


def test_ctrl_c_debounces_duplicate_dispatches():
    state = _InterruptState()
    assert not state.press(now=100.0)
    assert not state.press(now=100.1)
    assert state.press(now=101.0)


def test_ctrl_c_emergency_window_expires():
    state = _InterruptState()
    assert not state.press(now=100.0)
    assert not state.press(now=104.5)


def test_worker_prompt_does_not_cancel_for_permission_handoff():
    import inspect
    from locdex.cli.interactive import _active_task

    source = inspect.getsource(_active_task)
    assert "prompt.prompt_async(prompt_message)" in source
    assert "input_task.cancel()" not in source
    assert "broker.resolve(response, parsed)" in source
    assert 'signal.signal(signal.SIGINT, on_sigint)' in source
