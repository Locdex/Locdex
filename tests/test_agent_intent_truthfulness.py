from __future__ import annotations

from types import SimpleNamespace

from locdex import agent


class FakeRuntime:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def json_completion(self, messages, schema):
        del messages, schema
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return decision


def _config(steps=6):
    return SimpleNamespace(max_agent_steps=steps, model_key="smoke")


def test_natural_prefixed_edit_request_is_authorized():
    permission = agent._task_permission("now, just edit the 30 in config.py to 60")
    assert permission.can_edit is True


def test_observation_statement_remains_read_only():
    permission = agent._task_permission("it's still 30")
    assert permission.can_edit is False


def test_read_only_final_cannot_claim_workspace_change(monkeypatch, tmp_path):
    (tmp_path / "config.py").write_text("TIMEOUT = 30\n", encoding="utf-8")
    runtime = FakeRuntime(
        [
            {"action": "final", "summary": "Changed TIMEOUT from 30 to 60.", "confidence": 0.9},
            {"action": "final", "summary": "TIMEOUT is still 30 in config.py.", "confidence": 0.9},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "it's still 30",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "completed"
    assert result["summary"] == "TIMEOUT is still 30 in config.py."
    assert runtime.calls == 2


def test_repeated_false_mutation_claim_fails_closed(monkeypatch, tmp_path):
    (tmp_path / "config.py").write_text("TIMEOUT = 30\n", encoding="utf-8")
    runtime = FakeRuntime(
        [
            {"action": "final", "summary": "Changed TIMEOUT.", "confidence": 0.9},
            {"action": "final", "summary": "Updated config.py.", "confidence": 0.9},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "tell me what TIMEOUT is set to",
        repo_path=str(tmp_path),
        config=_config(),
    )

    assert result["status"] == "incomplete"
    assert "without mutation evidence" in result["summary"]
    assert runtime.calls == 2
