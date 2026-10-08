from __future__ import annotations

from locdex.routing.evidence import collect_cloud_evidence
from locdex.session.state import SessionState
from locdex.sandbox.policy import SandboxPolicy, SandboxMode
from locdex.security.policy import RiskClass


def test_cloud_evidence_aggregates_locally_and_redacts(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n\n"
        "def multiply(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_calculator.py").write_text(
        "from calculator import multiply\n"
        "def test_multiply():\n    assert multiply(2, 3) == 6\n",
        encoding="utf-8",
    )
    result = collect_cloud_evidence(
        str(tmp_path),
        "Fix multiply in calculator.py and run tests",
        context_limit=60000,
        local_failure="Model timed out. api_key=real_secret_12345",
    )
    assert result.tokens <= 5200
    assert "LOCDEX CLOUD EVIDENCE PACK" in result.text
    assert "calculator.py" in result.text
    assert "task_source" in result.sections or "retrieval_plan" in result.sections
    assert "real_secret_12345" not in result.text
    assert result.redactions >= 1


def test_default_sandbox_allows_network_but_dangerous_actions_still_denied():
    policy = SandboxPolicy()
    assert policy.mode is SandboxMode.WORKSPACE_NETWORK
    assert policy.authorize(tool="mcp_call", risk=RiskClass.NETWORK, args={}).allowed
    assert not policy.authorize(tool="arbitrary", risk=RiskClass.DANGEROUS, args={}).allowed


def test_new_session_defaults_to_network_without_updating_old_sessions(tmp_path):
    new_session = SessionState.create(repo_path=str(tmp_path), model="smoke")
    assert new_session.sandbox_mode == "workspace-network"
    old_session = SessionState.create(
        repo_path=str(tmp_path), model="smoke", sandbox_mode="workspace-write",
    )
    assert old_session.sandbox_mode == "workspace-write"
