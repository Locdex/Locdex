from __future__ import annotations

from types import SimpleNamespace

from locdex import agent, config


class FakeRuntime:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def json_completion(self, messages, schema):
        del messages, schema
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return decision


def test_agent_prints_progress_for_tool_calls(monkeypatch, tmp_path, capsys):
    runtime = FakeRuntime(
        [
            {"action": "tool", "tool": "write_file", "args": {"path": "app.py", "content": "VALUE = 2\n"}},
            {"action": "final", "summary": "Created app.py", "confidence": 0.9},
        ]
    )
    monkeypatch.setattr(agent, "get_runtime", lambda cfg: runtime)
    monkeypatch.setattr(agent, "record_usage", lambda source: None)

    result = agent.run_agent(
        "create app.py",
        repo_path=str(tmp_path),
        config=SimpleNamespace(max_agent_steps=4),
    )

    captured = capsys.readouterr().out
    assert result["status"] == "completed"
    assert "[Agent] Step 1/4: planning next action..." in captured
    assert "[Agent] Writing app.py..." in captured
    assert "[Agent] ✓ Updated app.py." in captured
    assert "[Agent] ✓ Task evidence satisfied." in captured


def test_smoke_model_gets_larger_default_step_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "selected_model_key", lambda: "smoke")
    monkeypatch.setattr(config, "locdex_cache_dir", lambda: tmp_path)
    monkeypatch.delenv("LOCDEX_MAX_AGENT_STEPS", raising=False)

    cfg = config.load_local_model_config("smoke")

    assert cfg.max_agent_steps == 20


def test_env_can_override_smoke_step_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "locdex_cache_dir", lambda: tmp_path)
    monkeypatch.setenv("LOCDEX_MAX_AGENT_STEPS", "7")

    cfg = config.load_local_model_config("smoke")

    assert cfg.max_agent_steps == 7
