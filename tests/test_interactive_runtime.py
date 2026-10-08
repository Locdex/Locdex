from __future__ import annotations

import asyncio
import time

import pytest

from locdex.cli.activity import ActivityState
from locdex.cli.interactive import _ApprovalBroker
from locdex.runtime.isolated import IsolatedLlamaCppSession
from locdex.runtime.llama_cpp import RuntimeExecutionError
from locdex.security import ApprovalChoice


class _SlowPipe:
    def __init__(self):
        self.closed = False

    def poll(self, timeout):
        time.sleep(min(0.01, timeout))
        return False

    def close(self):
        self.closed = True

    def send(self, value):
        pass


class _DummyProcess:
    def __init__(self):
        self.alive = True
        self.terminated = False

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.alive = False
        self.terminated = True

    def join(self, timeout=None):
        pass

    def kill(self):
        self.terminate()


def test_hung_local_model_call_is_terminated():
    session = IsolatedLlamaCppSession(model_key="smoke", timeout_seconds=0.03)
    parent, process = _SlowPipe(), _DummyProcess()
    session._parent = parent
    session._process = process
    with pytest.raises(RuntimeExecutionError, match="timed out"):
        session._receive(time.monotonic() + 0.03, "generating")
    assert process.terminated
    assert parent.closed


def test_cancelled_local_model_call_is_terminated():
    session = IsolatedLlamaCppSession(
        model_key="smoke", timeout_seconds=10.0, cancelled=lambda: True,
    )
    parent, process = _SlowPipe(), _DummyProcess()
    session._parent = parent
    session._process = process
    with pytest.raises(RuntimeExecutionError, match="cancelled"):
        session._receive(time.monotonic() + 10, "generating")
    assert process.terminated


def test_inference_progress_updates_live_status():
    activity = ActivityState()
    assert "Loading local model" in activity.on_progress("[Inference] Loading local model...")
    assert "Loading local model" in activity.toolbar(frame=1)
    assert "Generating model decision" in activity.on_progress("[Inference] Generating model decision...")
    assert "Generating model decision" in activity.toolbar(frame=2)


def test_permission_broker_resumes_agent_on_approval():
    async def run():
        broker = _ApprovalBroker(asyncio.get_running_loop())
        requester = asyncio.create_task(asyncio.to_thread(broker.request, "permission"))
        request, response = await asyncio.wait_for(broker.pending.get(), 2)
        assert request == "permission"
        broker.resolve(response, ApprovalChoice.ALLOW_ONCE)
        assert await asyncio.wait_for(requester, 2) == ApprovalChoice.ALLOW_ONCE

    asyncio.run(run())


def test_live_header_contains_permission_and_controls_above_input():
    import inspect
    from locdex.cli.interactive import _active_task

    source = inspect.getsource(_active_task)
    assert "message=prompt_message" in source
    assert "bottom_toolbar=" not in source
    assert "format_permission_request(request)" in source
    assert "[y] Allow once" in source
    assert "[a] Allow similar this session" in source
    assert "[n] Deny" in source
    assert "local_session=local_session" in source
    assert "local_session.close()" in source
