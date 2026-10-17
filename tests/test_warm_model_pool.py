"""A warmed isolated model is reused across interactive tasks without leaking task state."""
from __future__ import annotations

import pytest

from locdex.runtime.model_pool import WarmModelPool


class FakeWorker:
    instances = []

    def __init__(self, *, model_key):
        self.model_key = model_key
        self.worker_status = "unloaded"
        self.closed = False
        self.preloads = 0
        self.callbacks = []
        self.__class__.instances.append(self)

    def preload(self):
        self.preloads += 1
        self.worker_status = "loading"

    def configure_task(self, **kwargs):
        self.callbacks.append(kwargs)

    def close(self):
        self.closed = True
        self.worker_status = "stopped"


def test_preload_then_two_tasks_reuse_single_worker():
    FakeWorker.instances = []
    pool = WarmModelPool(session_factory=FakeWorker)
    assert pool.status == "unloaded"
    first = pool.start("qwen25-3b")
    assert pool.status == "loading"
    assert first.preloads == 1
    cancel = lambda: False
    reused = pool.for_task("qwen25-3b", cancelled=cancel, progress=lambda x: None)
    assert reused is first
    assert first.preloads == 1
    assert first.callbacks[-1]["cancelled"] is cancel
    pool.release_task(reused)
    assert first.callbacks[-1]["progress"] is None
    second = pool.for_task("qwen25-3b", cancelled=lambda: False, progress=None)
    assert second is first
    assert len(FakeWorker.instances) == 1
    pool.close()
    assert first.closed
    assert pool.status == "unloaded"


def test_switching_models_closes_old_worker():
    FakeWorker.instances = []
    pool = WarmModelPool(session_factory=FakeWorker)
    old = pool.start("qwen25-3b")
    new = pool.start("smoke")
    assert old.closed
    assert not new.closed
    assert pool.model_key == "smoke"
    pool.close()
    assert new.closed


def test_failed_worker_recreated_before_next_task():
    FakeWorker.instances = []
    pool = WarmModelPool(session_factory=FakeWorker)
    old = pool.start("qwen25-3b")
    old.worker_status = "failed"
    new = pool.start("qwen25-3b")
    assert new is not old
    assert old.closed
    assert len(FakeWorker.instances) == 2
    pool.close()


def test_preload_failure_closes_worker_and_does_not_cache():
    class BrokenWorker(FakeWorker):
        def preload(self):
            raise RuntimeError("model initialization process unavailable")

    pool = WarmModelPool(session_factory=BrokenWorker)
    with pytest.raises(RuntimeError, match="unavailable"):
        pool.start("qwen25-3b")
    assert pool.model_key is None
    assert pool.status == "unloaded"
    assert BrokenWorker.instances[-1].closed


def test_standalone_session_nonblocking_preload_is_documented():
    from locdex.runtime.isolated import IsolatedLlamaCppSession
    import inspect
    code = inspect.getsource(IsolatedLlamaCppSession.preload)
    assert "self._ensure_started()" in code
    assert "self._receive" not in code


def test_pool_is_closed_after_interactive_loop_returns(monkeypatch, tmp_path):
    from locdex.cli import interactive
    seen = []

    class FakePool:
        def close(self):
            seen.append("closed")

    def fake_loop(repo_path, *, resume_id, model_pool):
        seen.append(("running", repo_path, resume_id))
        return 0

    monkeypatch.setattr(interactive, "WarmModelPool", FakePool)
    monkeypatch.setattr(interactive, "_run_interactive_impl", fake_loop)
    assert interactive.run_interactive(str(tmp_path)) == 0
    assert seen[-1] == "closed"


def test_nonblocking_ready_handshake_is_reused_without_reloading():
    from locdex.runtime.isolated import IsolatedLlamaCppSession

    class FakeProcess:
        def is_alive(self):
            return True

    class FakePipe:
        def __init__(self):
            self.events = [("ready", {"loading_seconds": 1.25})]

        def poll(self, timeout):
            return bool(self.events)

        def recv(self):
            return self.events.pop(0)

    session = IsolatedLlamaCppSession(model_key="smoke", timeout_seconds=5)
    session._process = FakeProcess()
    session._parent = FakePipe()
    assert session.worker_status == "ready"
    assert session._ready is True
    assert session._loading_seconds == 1.25
    assert session.worker_status == "ready"
    assert session._parent.events == []
    # Only fake handles are attached; no subprocess or model is started.
    session._process = None
    session._parent = None
    session.close()
