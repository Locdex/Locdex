from __future__ import annotations

from types import SimpleNamespace

from locdex.routing import execution
from locdex.runtime.llama_cpp import RuntimeExecutionError
from locdex.providers.openai_compatible import CloudConfig


class FakeEngine:
    model_key = "smoke"
    _last_failure_rollback = ["calculator.py"]

    def __init__(self, model_key="smoke", cloud=False):
        self.model_key = model_key
        self.cloud = cloud

    def execute(self, task, repo_path, **kwargs):
        if not self.cloud:
            raise RuntimeExecutionError(
                "Local inference generating timed out after 45s; model process terminated."
            )
        assert kwargs["session"] is not None
        return {
            "status": "completed", "model": "configured-cloud", "steps": 2,
            "summary": "Cloud completed after local timeout.",
            "verification": {"passed": True}, "files_modified": ["calculator.py"],
        }


class CloudSession:
    input_tokens = 17
    output_tokens = 9
    latency_ms = 50
    cost_usd = 0.001


def config(enabled=True):
    return CloudConfig(
        enabled=enabled,
        provider="test-provider",
        model="test-cloud-model",
        base_url="https://cloud.example/v1",
        api_key="fake",
    )


def setup(monkeypatch, enabled=True):
    monkeypatch.setattr(execution.CloudConfig, "from_env", classmethod(lambda cls: config(enabled)))
    monkeypatch.setattr(execution, "make_cloud_session", lambda conf: CloudSession())
    monkeypatch.setattr(execution, "AgentEngine", lambda model_key: FakeEngine(model_key, cloud=True))
    monkeypatch.setattr(execution, "_safe_record_outcome", lambda **kwargs: None)
    monkeypatch.setattr(
        execution, "collect_cloud_evidence",
        lambda *args, **kwargs: SimpleNamespace(
            text="## task_source\\nrelevant calculator fixture",
            tokens=12, sections=("task_source",), redactions=0,
        ),
    )


def test_local_timeout_falls_back_to_configured_cloud(monkeypatch):
    setup(monkeypatch)
    progress = []
    result = execution.execute_with_escalation(
        FakeEngine(),
        "repair calculator",
        ".",
        local_session=object(),
        sandbox_mode="workspace-network",
        progress=progress.append,
    )
    assert result["status"] == "completed"
    assert result["route"] == "cloud"
    assert result["cloud_escalation"]["reason"] == "inference_timeout"
    assert result["local_attempt"]["rolled_back_files"] == ["calculator.py"]
    assert "test-provider" in " ".join(progress)


def test_no_cloud_configuration_does_not_attempt_network(monkeypatch):
    setup(monkeypatch, enabled=False)
    result = execution.execute_with_escalation(
        FakeEngine(), "repair", ".", local_session=object(),
        sandbox_mode="workspace-network",
    )
    assert result["status"] == "error"
    assert result["cloud_escalation"]["reason"] == "cloud_not_configured"


def test_sandbox_blocks_cloud_escalation(monkeypatch):
    setup(monkeypatch)
    result = execution.execute_with_escalation(
        FakeEngine(), "repair", ".", local_session=object(),
        sandbox_mode="workspace-write",
    )
    assert result["status"] == "error"
    assert result["cloud_escalation"]["reason"] == "sandbox_network_disabled"


def test_cancel_never_escalates_to_cloud(monkeypatch):
    setup(monkeypatch)
    cancelled = SimpleNamespace(cancelled=True)
    result = execution.execute_with_escalation(
        FakeEngine(), "repair", ".", local_session=object(),
        sandbox_mode="workspace-network", steering_queue=cancelled,
    )
    assert result["status"] == "cancelled"
    assert result["cloud_escalation"]["attempted"] is False

def test_cloud_releases_local_model_and_carries_undo_journal(monkeypatch):
    setup(monkeypatch)

    class Closable:
        closed = False

        def close(self):
            self.closed = True

    local_session = Closable()
    local_engine = FakeEngine()
    # Real cloud engines populate their own ChangeJournal while editing.
    cloud_journal = object()

    def cloud_factory(model_key):
        cloud = FakeEngine(model_key, cloud=True)
        cloud.change_journal = cloud_journal
        return cloud

    monkeypatch.setattr(execution, "AgentEngine", cloud_factory)
    result = execution.execute_with_escalation(
        local_engine, "fix bug", ".", local_session=local_session,
        sandbox_mode="workspace-network",
    )
    assert local_session.closed
    assert result["status"] == "completed"
    assert local_engine.change_journal is cloud_journal
