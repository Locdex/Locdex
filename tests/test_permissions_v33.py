from __future__ import annotations

from locdex.agent import AgentEngine
from locdex.security import (
    ApprovalChoice,
    PermissionController,
    PermissionMode,
    RiskClass,
    build_tool_preview,
    format_permission_request,
)


def test_plan_mode_allows_reads_and_denies_writes(tmp_path):
    controller = PermissionController(PermissionMode.PLAN)

    read = controller.authorize(
        repo_path=str(tmp_path),
        tool="read_file",
        risk=RiskClass.READ,
        args={"path": "app.py"},
    )
    write = controller.authorize(
        repo_path=str(tmp_path),
        tool="replace_in_file",
        risk=RiskClass.WRITE,
        args={"path": "app.py", "old": "1", "new": "2"},
    )

    assert read.allowed is True
    assert write.allowed is False
    assert "plan" in write.reason


def test_ask_mode_denial_prevents_workspace_mutation(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    original = target.read_text(encoding="utf-8")

    requests = []

    def deny(request):
        requests.append(request)
        return ApprovalChoice.DENY

    controller = PermissionController(
        PermissionMode.ASK,
        approval_callback=deny,
    )
    engine = AgentEngine(model_key="smoke")
    engine.permission_controller = controller

    result = engine._run_tool(
        repo_path=str(tmp_path),
        task="Change VALUE in app.py to 2.",
        name="replace_in_file",
        args={
            "path": "app.py",
            "old": "VALUE = 1",
            "new": "VALUE = 2",
        },
        progress=None,
    )

    assert result["permission_denied"] is True
    assert target.read_text(encoding="utf-8") == original
    assert len(requests) == 1
    assert "-VALUE = 1" in requests[0].preview
    assert "+VALUE = 2" in requests[0].preview


def test_allow_session_caches_similar_write_approval(tmp_path):
    calls = []

    def allow_session(request):
        calls.append(request.tool)
        return ApprovalChoice.ALLOW_SESSION

    controller = PermissionController(
        PermissionMode.ASK,
        approval_callback=allow_session,
    )

    first = controller.authorize(
        repo_path=str(tmp_path),
        tool="replace_in_file",
        risk=RiskClass.WRITE,
        args={"path": "a.py", "old": "1", "new": "2"},
    )
    second = controller.authorize(
        repo_path=str(tmp_path),
        tool="replace_symbol",
        risk=RiskClass.WRITE,
        args={
            "path": "b.py",
            "name": "run",
            "new_source": "def run():\n    return 2",
        },
    )

    assert first.allowed is True
    assert second.allowed is True
    assert calls == ["replace_in_file"]
    assert second.choice is ApprovalChoice.ALLOW_SESSION


def test_auto_edit_allows_writes_but_not_commands_without_approval(tmp_path):
    controller = PermissionController(PermissionMode.AUTO_EDIT)

    write = controller.authorize(
        repo_path=str(tmp_path),
        tool="write_file",
        risk=RiskClass.WRITE,
        args={"path": "new.py", "content": "VALUE = 1\n"},
    )
    command = controller.authorize(
        repo_path=str(tmp_path),
        tool="run_command",
        risk=RiskClass.EXECUTE,
        args={"argv": ["python", "-m", "pytest"]},
    )

    assert write.allowed is True
    assert command.allowed is False
    assert "interactive approval" in command.reason


def test_trusted_allows_execute_but_still_requires_git_approval(tmp_path):
    controller = PermissionController(PermissionMode.TRUSTED)

    execute = controller.authorize(
        repo_path=str(tmp_path),
        tool="run_tests",
        risk=RiskClass.EXECUTE,
        args={},
    )
    git = controller.authorize(
        repo_path=str(tmp_path),
        tool="git_push",
        risk=RiskClass.GIT_WRITE,
        args={},
    )

    assert execute.allowed is True
    assert git.allowed is False


def test_replace_symbol_preview_shows_before_and_after(tmp_path):
    target = tmp_path / "app.py"
    target.write_text(
        "def value():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    preview = build_tool_preview(
        str(tmp_path),
        "replace_symbol",
        {
            "path": "app.py",
            "name": "value",
            "new_source": "def value():\n    return 2",
        },
    )

    assert "-    return 1" in preview
    assert "+    return 2" in preview


def test_plan_mode_blocks_structured_verification_execution(tmp_path):
    from locdex.verification import VerificationEngine

    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "def test_value():\n    assert 1 == 1\n",
        encoding="utf-8",
    )

    verifier = VerificationEngine(
        permission_controller=PermissionController(PermissionMode.PLAN)
    )
    result = verifier.verify(str(tmp_path), ["app.py"])

    checks = {check.name: check for check in result.checks}
    assert result.passed is False
    assert checks["compile"].status == "failed"
    assert "Permission denied" in checks["compile"].output
    assert checks["tests"].status == "failed"
    assert "Permission denied" in checks["tests"].output


def test_permission_request_describes_reason_and_access(tmp_path):
    seen = []

    def capture(request):
        seen.append(request)
        return ApprovalChoice.DENY

    controller = PermissionController(
        PermissionMode.ASK,
        approval_callback=capture,
    )
    controller.authorize(
        repo_path=str(tmp_path),
        tool="run_tests",
        risk=RiskClass.EXECUTE,
        args={},
    )

    request = seen[0]
    rendered = format_permission_request(request)
    assert "Verify the current workspace changes." in rendered
    assert "execute:local-process" in rendered
    assert "Run the detected project test suite." in rendered
