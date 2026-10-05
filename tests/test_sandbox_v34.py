from __future__ import annotations

from locdex.sandbox import (
    SandboxCapabilities,
    SandboxMode,
    SandboxPolicy,
    sandbox_environment,
)
from locdex.sandbox import runner
from locdex.security import RiskClass
from locdex.tools import executor


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


def test_windows_without_helper_is_reported_as_logical(monkeypatch):
    monkeypatch.setattr(runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runner, "windows_helper_path", lambda: None)

    caps = runner.detect_sandbox_capabilities()

    assert caps.backend == "logical"
    assert caps.os_isolation is False
    assert caps.process_isolation is False


def test_windows_native_helper_reports_process_isolation(tmp_path, monkeypatch):
    helper = tmp_path / "locdex-windows-sandbox.exe"
    helper.write_bytes(b"helper")
    monkeypatch.setattr(runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runner, "windows_helper_path", lambda: helper)
    monkeypatch.setattr(
        runner,
        "_probe_windows_helper",
        lambda path: {
            "process_isolation": True,
            "filesystem_isolation": False,
            "network_isolation": False,
        },
    )

    caps = runner.detect_sandbox_capabilities()

    assert caps.backend == "windows-native"
    assert caps.os_isolation is True
    assert caps.process_isolation is True
    assert caps.filesystem_isolation is False
    assert caps.network_isolation is False


def test_windows_native_wrapper_invokes_helper(tmp_path, monkeypatch):
    helper = tmp_path / "locdex-windows-sandbox.exe"
    helper.write_bytes(b"helper")
    monkeypatch.setattr(runner, "windows_helper_path", lambda: helper)
    monkeypatch.setattr(
        runner,
        "detect_sandbox_capabilities",
        lambda: SandboxCapabilities(
            platform="windows",
            backend="windows-native",
            os_isolation=True,
            process_isolation=True,
            network_isolation=False,
            filesystem_isolation=False,
            helper_path=str(helper),
            reason="test",
        ),
    )

    argv, backend = runner.wrap_command(
        str(tmp_path),
        str(tmp_path),
        ["python", "-m", "pytest"],
        SandboxMode.WORKSPACE_WRITE,
    )

    assert backend == "windows-native"
    assert argv[0] == str(helper)
    assert argv[1:3] == ["run", "--workspace"]
    assert "--cwd" in argv
    assert "--mode" in argv
    assert argv[-3:] == ["python", "-m", "pytest"]


def test_dedicated_git_uses_sandbox_wrapper(tmp_path, monkeypatch):
    seen = {}

    def fake_wrap(repo_path, cwd, argv, mode):
        seen["repo"] = repo_path
        seen["cwd"] = cwd
        seen["argv"] = list(argv)
        seen["mode"] = mode
        return ["sandbox", *argv], "test-backend"

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["executed"] = list(argv)
        seen["env"] = dict(kwargs["env"])
        return Result()

    monkeypatch.setattr(executor, "wrap_command", fake_wrap)
    monkeypatch.setattr(executor.subprocess, "run", fake_run)

    result = executor._git(
        str(tmp_path),
        "status",
        "--short",
        sandbox_mode="workspace-write",
    )

    assert result.returncode == 0
    assert seen["argv"] == ["git", "status", "--short"]
    assert seen["executed"] == ["sandbox", "git", "status", "--short"]
    assert seen["mode"] == "workspace-write"
    assert seen["env"]["LOCDEX_SANDBOX_MODE"] == "workspace-write"
