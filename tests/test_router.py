from unittest.mock import patch

from locdex.router import route_task


@patch("locdex.router.validate_candidate_set")
@patch("locdex.router.run_cloud")
@patch("locdex.router.run_local_with_confidence")
def test_router_falls_back_to_cloud_and_applies_validated_files(
    mock_run_local,
    mock_run_cloud,
    mock_validate,
    tmp_path,
):
    """A local-agent escalation should use the configured cloud fallback once."""
    mock_run_local.return_value = {
        "status": "escalate",
        "confidence": 0.0,
        "summary": "Local agent requested escalation",
    }
    mock_run_cloud.return_value = {
        "files": [{"filepath": "test.py", "code": "print('cloud success')\n"}],
        "confidence": 0.9,
    }
    mock_validate.return_value = {
        "all_pass": True,
        "message": "candidate validated",
    }

    context = {
        "repo_path": str(tmp_path),
        "system_prompt": "Mock system prompt",
    }
    result = route_task("Fix this bug", "general_task", context, {})

    mock_run_local.assert_called_once()
    mock_run_cloud.assert_called_once()
    mock_validate.assert_called_once()
    assert result["source"] == "cloud"
    assert result["result"]["status"] == "completed"
    assert (tmp_path / "test.py").read_text(encoding="utf-8") == "print('cloud success')\n"


@patch("locdex.router.run_cloud")
@patch("locdex.router.run_local_with_confidence")
def test_router_returns_completed_local_result_without_cloud(
    mock_run_local,
    mock_run_cloud,
    tmp_path,
):
    """A completed local-agent task must not invoke cloud fallback."""
    local_result = {
        "status": "completed",
        "confidence": 0.92,
        "summary": "Task completed locally",
        "steps": 2,
        "tool_calls": [],
    }
    mock_run_local.return_value = local_result

    result = route_task(
        "Refactor this function",
        "general_task",
        {"repo_path": str(tmp_path)},
        {},
    )

    assert result == {
        "source": "local",
        "result": local_result,
        "escalation_reason": None,
    }
    mock_run_cloud.assert_not_called()
