from __future__ import annotations

from locdex.agent import AgentEngine
from locdex.verification import VerificationEngine


def test_preexisting_git_status_paths_are_parsed():
    paths = AgentEngine._preexisting_changed_paths(
        {
            "ok": True,
            "output": (
                "## feature\n"
                " M app.py\n"
                "?? notes.txt\n"
                "R  old_name.py -> new_name.py\n"
            ),
        }
    )
    assert paths == {"app.py", "notes.txt", "new_name.py"}


def test_verifier_skips_ruff_when_repo_does_not_configure_it(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")

    result = VerificationEngine().verify(str(tmp_path), ["app.py"])

    lint = next(check for check in result.checks if check.name == "lint")
    assert lint.status == "skipped"
    assert "does not declare Ruff" in lint.output
