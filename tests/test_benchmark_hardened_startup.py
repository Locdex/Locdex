"""Regression checks for startup phases in the actual hardened Locdex agent."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from locdex.agent import hardened
from locdex.agent import engine as base_engine


class StopStartup(Exception):
    pass


def _retrieval_plan():
    return SimpleNamespace(
        initial_actions=[],
        primary_files=[],
        likely_change_files=[],
        missing_symbols=[],
    )


def test_hardened_agent_identifies_model_loading_before_slow_constructor(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(hardened, "plan_retrieval", lambda *args, **kwargs: _retrieval_plan())

    def cannot_load_model(**kwargs):
        raise StopStartup("simulated model load delay")

    monkeypatch.setattr(hardened, "LlamaCppSession", cannot_load_model)
    runner = hardened.AgentEngine(model_key="qwen25-3b")
    with pytest.raises(StopStartup):
        runner.execute("Fix the nonnegative difference bug", str(tmp_path), progress=events.append)
    assert any("Preparing protected workspace" in event for event in events)
    assert any("Planning repository retrieval" in event for event in events)
    assert any("Retrieval planning complete" in event for event in events)
    assert any("[Inference] Loading qwen25-3b" in event for event in events)
    assert not any("Model ready" in event for event in events)


def test_hardened_agent_reports_model_ready_before_base_execution(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(hardened, "plan_retrieval", lambda *args, **kwargs: _retrieval_plan())
    monkeypatch.setattr(hardened, "LlamaCppSession", lambda **kwargs: object())

    def stop_before_base_execution(*args, **kwargs):
        raise StopStartup("stop after load")

    monkeypatch.setattr(base_engine.AgentEngine, "execute", stop_before_base_execution)
    runner = hardened.AgentEngine(model_key="qwen25-3b")
    with pytest.raises(StopStartup):
        runner.execute("Fix the nonnegative difference bug", str(tmp_path), progress=events.append)
    assert any("Model ready" in event for event in events)
