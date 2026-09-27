import pytest

from locdex.agent_tools import (
    ToolError,
    list_files,
    read_file,
    replace_in_file,
    run_command,
    search_code,
    write_file,
)


def test_tools_inspect_and_edit_repo_without_leaving_root(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    listing = list_files(str(tmp_path))
    assert "src/app.py" in listing["files"]

    content = read_file(str(tmp_path), "src/app.py")
    assert "def hello" in content["content"]

    matches = search_code(str(tmp_path), "world")
    assert matches["matches"][0]["path"] == "src/app.py"

    replace_in_file(str(tmp_path), "src/app.py", "world", "locdex")
    assert "locdex" in (src / "app.py").read_text(encoding="utf-8")

    write_file(str(tmp_path), "src/new.py", "VALUE = 2\n")
    assert (src / "new.py").read_text(encoding="utf-8") == "VALUE = 2\n"


def test_read_file_blocks_traversal(tmp_path):
    with pytest.raises(ToolError):
        read_file(str(tmp_path), "../outside.txt")


def test_run_command_cannot_bypass_dedicated_git_tools(tmp_path):
    with pytest.raises(ToolError):
        run_command(str(tmp_path), ["git", "status"])
