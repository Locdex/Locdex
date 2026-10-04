from __future__ import annotations

from locdex.sandbox import (
    SandboxCapabilities,
    SandboxMode,
    SandboxPolicy,
    sandbox_environment,
)
from locdex.sandbox import runner
from locdex.security import RiskClass


def test_read_only_sandbox_denies_mutation_and_execution():
    policy = SandboxPolicy(SandboxMode.READ_ONLY)

    assert policy.authorize(
        tool="read_file",
        risk=RiskClass.READ,
        args={"path": "app.py"},
    ).allowed
    assert not policy.authorize(
        tool="replace_in_file",
        risk=RiskClass.WRITE,
        args={"path": "app.py"},
    ).allowed
    assert not policy.authorize(
        tool="run_tests",
        risk=RiskClass.EXECUTE,
        args={},
    ).allowed


def test_workspace_write_blocks_network_and_remote_git():
    policy = SandboxPolicy(SandboxMode.WORKSPACE_WRITE)

    assert policy.authorize(
        tool="replace_in_file",
        risk=RiskClass.WRITE,
        args={"path": "app.py"},
    ).allowed
    assert policy.authorize(
        tool="run_tests",
        risk=RiskClass.EXECUTE,
        args={},
    ).allowed
    assert not policy.authorize(
        tool="git_push",
        risk=RiskClass.GIT_WRITE,
        args={"remote": "origin"},
    ).allowed
    assert not policy.authorize(
        tool="run_command",
        risk=RiskClass.EXECUTE,
        args={"argv": ["npm", "install"]},
    ).allowed


def test_workspace_network_allows_remote_capabilities():
    policy = SandboxPolicy(SandboxMode.WORKSPACE_NETWORK)

    assert policy.authorize(
        tool="git_push",
        risk=RiskClass.GIT_WRITE,
        args={"remote": "origin"},
    ).allowed
    assert policy.authorize(
        tool="run_command",
        risk=RiskClass.EXECUTE,
        args={"argv": ["npm", "test"]},
    ).allowed


def test_network_disabled_environment_sets_proxy_blockers():
    env = sandbox_environment(SandboxMode.WORKSPACE_WRITE)

    assert env["LOCDEX_SANDBOX_NETWORK"] == "0"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert env["NO_PROXY"] == "*"


def test_bubblewrap_wrapper_binds_workspace_and_unshares_network(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner,
        "detect_sandbox_capabilities",
        lambda: SandboxCapabilities(
            platform="linux",
            backend="bubblewrap",
            os_isolation=True,
            network_isolation=True,
            filesystem_isolation=True,
            reason="test",
        ),
    )

    argv, backend = runner.wrap_command(
        str(tmp_path),
        str(tmp_path),
        ["python", "-m", "pytest"],
        SandboxMode.WORKSPACE_WRITE,
    )

    assert backend == "bubblewrap"
    assert argv[0] == "bwrap"
    assert "--unshare-net" in argv
    assert "--bind" in argv
    assert str(tmp_path.resolve()) in argv
    assert argv[-3:] == ["python", "-m", "pytest"]


def test_windows_capability_is_reported_as_logical(monkeypatch):
    monkeypatch.setattr(runner.platform, "system", lambda: "Windows")

    caps = runner.detect_sandbox_capabilities()

    assert caps.backend == "logical"
    assert caps.os_isolation is False
    assert "AppContainer" in caps.reason
