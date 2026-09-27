from __future__ import annotations

import pytest

from locdex import agent_tools


def test_write_file_reports_noop_when_content_is_identical(tmp_path):
    target = tmp_path / "config.py"
    target.write_text("TIMEOUT = 30\n", encoding="utf-8")

    result = agent_tools.write_file(str(tmp_path), "config.py", "TIMEOUT = 30\n")

    assert result["ok"] is True
    assert result["changed"] is False
    assert target.read_text(encoding="utf-8") == "TIMEOUT = 30\n"


def test_write_file_verifies_real_change(tmp_path):
    target = tmp_path / "config.py"
    target.write_text("TIMEOUT = 30\n", encoding="utf-8")

    result = agent_tools.write_file(str(tmp_path), "config.py", "TIMEOUT = 60\n")

    assert result["ok"] is True
    assert result["changed"] is True
    assert target.read_text(encoding="utf-8") == "TIMEOUT = 60\n"


def test_replace_in_file_rejects_identical_old_new(tmp_path):
    target = tmp_path / "config.py"
    target.write_text("TIMEOUT = 30\n", encoding="utf-8")

    with pytest.raises(agent_tools.ToolError, match="identical"):
        agent_tools.replace_in_file(
            str(tmp_path),
            "config.py",
            "TIMEOUT = 30",
            "TIMEOUT = 30",
        )


def test_replace_in_file_reports_verified_change(tmp_path):
    target = tmp_path / "config.py"
    target.write_text("TIMEOUT = 30\n", encoding="utf-8")

    result = agent_tools.replace_in_file(
        str(tmp_path),
        "config.py",
        "TIMEOUT = 30",
        "TIMEOUT = 60",
    )

    assert result["ok"] is True
    assert result["changed"] is True
    assert target.read_text(encoding="utf-8") == "TIMEOUT = 60\n"
