from src.locdex.agent import _git_tool_allowed


def test_git_operations_require_explicit_user_intent():
    assert not _git_tool_allowed("fix the login bug", "git_commit")
    assert _git_tool_allowed("commit these changes with a sensible message", "git_commit")
    assert _git_tool_allowed("pull latest from origin", "git_pull")
    assert _git_tool_allowed("push this branch", "git_push")
    assert _git_tool_allowed("ship it", "git_add")
    assert _git_tool_allowed("ship it", "git_commit")
    assert _git_tool_allowed("ship it", "git_push")
