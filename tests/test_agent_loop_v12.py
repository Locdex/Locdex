from pathlib import Path

from locdex import agent
from locdex.config import LocalModelConfig


class FakeRuntime:
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def json_completion(self, messages, schema):
        return next(self.decisions)


def _config(tmp_path: Path):
    return LocalModelConfig(
        model_key="qwen",
        repo_id="example/repo",
        filename_pattern="*.gguf",
        revision=None,
        expected_sha256=None,
        explicit_model_path=None,
        cache_dir=tmp_path,
        auto_download=False,
        n_ctx=4096,
        n_threads=2,
        n_gpu_layers=0,
        max_tokens=1024,
        temperature=0.1,
        max_agent_steps=4,
    )


def test_agent_writes_directly_to_workspace(monkeypatch, tmp_path):
    runtime = FakeRuntime([
        {"action": "tool", "tool": "write_file", "args": {"path": "app.py", "content": "VALUE = 2\n"}},
        {"action": "final", "summary": "Updated app.py", "confidence": 0.9},
    ])
    monkeypatch.setattr(agent, "get_runtime", lambda config: runtime)

    result = agent.run_agent("create app.py", repo_path=str(tmp_path), config=_config(tmp_path))

    assert result["status"] == "completed"
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"


def test_agent_cannot_commit_without_explicit_user_request(monkeypatch, tmp_path):
    runtime = FakeRuntime([
        {"action": "tool", "tool": "git_commit", "args": {"message": "unexpected"}},
        {"action": "final", "summary": "No commit performed", "confidence": 0.8},
    ])
    monkeypatch.setattr(agent, "get_runtime", lambda config: runtime)

    result = agent.run_agent("fix app.py", repo_path=str(tmp_path), config=_config(tmp_path))

    assert result["status"] == "completed"
    first_result = result["tool_calls"][0]["result"]
    assert "requires an explicit Git instruction" in first_result["error"]
