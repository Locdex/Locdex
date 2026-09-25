from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .safety import check_ast_security, is_protected_path, is_safe_path

COPY_IGNORE = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".locdex-preflight-tmp",
    ".pytest-locdex",
    "build",
    "dist",
}


@dataclass
class SandboxResult:
    """Backward-compatible result name for staged validation commands.

    The current implementation does not use Docker. Commands run in a disposable
    copy of the repository with a reduced environment and no shell invocation.
    """

    returncode: int
    stdout: str
    stderr: str = ""


def detect_language(filepath: str) -> str:
    if filepath.endswith(".py"):
        return "python"
    return "unknown"


def quick_check(code: str, language: str = "python") -> bool:
    if language != "python":
        return False
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def _copy_workspace(repo_path: str, destination: str) -> None:
    source = Path(repo_path).resolve()
    if not source.is_dir():
        raise ValueError(f"Repository path does not exist: {source}")

    destination_path = Path(destination).resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name in COPY_IGNORE or name.startswith(".locdex-")}
        current = Path(directory).resolve()

        # Never copy a destination that happens to live below the source back
        # into itself. This is especially important during Windows preflight,
        # where TEMP is intentionally redirected into a repo-local directory.
        for name in names:
            candidate = (current / name).resolve()
            try:
                destination_path.relative_to(candidate)
            except ValueError:
                continue
            ignored.add(name)

        return ignored

    shutil.copytree(source, destination_path, dirs_exist_ok=True, ignore=ignore)


def _stage_tempdir(repo_path: str) -> tempfile.TemporaryDirectory[str]:
    """Create staging beside the repository, never inside the repository tree."""
    source = Path(repo_path).resolve()
    if not source.is_dir():
        raise ValueError(f"Repository path does not exist: {source}")
    return tempfile.TemporaryDirectory(prefix=".locdex-stage-", dir=str(source.parent))


def _stage_candidates(staged_repo: str, files: list[dict]) -> tuple[bool, str, list[str]]:
    staged_paths: list[str] = []
    for item in files:
        filepath = str(item.get("filepath", "")).strip()
        code = item.get("code")
        if not filepath or not isinstance(code, str):
            return False, "Candidate contains an invalid filepath or code payload.", []
        if not filepath.endswith(".py"):
            return False, f"Locdex validation currently supports Python candidate validation only: {filepath}", []
        if not is_safe_path(staged_repo, filepath) or is_protected_path(filepath):
            return False, f"Security boundary violation: {filepath}", []

        try:
            compile(code, filepath, "exec")
        except SyntaxError as exc:
            return False, f"Syntax Error in {filepath}: {exc}", []

        flags = check_ast_security(code)
        if flags:
            return False, f"Security review failed for {filepath}:\n" + "\n".join(flags), []

        target = (Path(staged_repo) / filepath).resolve()
        root = Path(staged_repo).resolve()
        if os.path.commonpath([str(root), str(target)]) != str(root):
            return False, f"Path traversal blocked: {filepath}", []
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
        staged_paths.append(filepath)

    return True, "", staged_paths


def _validation_env() -> dict[str, str]:
    """Return a reduced environment for staged host-side validation.

    This is not a security sandbox. The disposable copy protects the real working
    tree from ordinary test/lint mutations, while shell=False and a constrained
    environment reduce accidental side effects. Strong isolation can be added in
    a later release without making Docker a v0.1 requirement.
    """
    keep = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TMP",
        "TEMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
    }
    env = {key: value for key, value in os.environ.items() if key in keep}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["LOCDEX_AUTO_DOWNLOAD"] = "0"
    return env


def _run_staged_process(cmd: list[str], workspace: str, timeout: int) -> tuple[SandboxResult | None, str | None]:
    try:
        completed = subprocess.run(
            cmd,
            cwd=workspace,
            env=_validation_env(),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"Execution timed out after {timeout} seconds."
    except OSError as exc:
        return None, f"Could not execute {cmd[0]!r}: {exc}"
    return SandboxResult(completed.returncode, completed.stdout, completed.stderr), None


def run_sandboxed(cmd: list[str], timeout: int = 45, repo_path: str = "."):
    """Backward-compatible API: run a command in a disposable staged workspace.

    Despite the legacy function name, Docker is not used in the current release.
    """
    with _stage_tempdir(repo_path) as temp_dir:
        staged_repo = os.path.join(temp_dir, "repo")
        try:
            _copy_workspace(repo_path, staged_repo)
        except (OSError, ValueError, shutil.Error) as exc:
            return None, f"Could not stage repository: {exc}"
        return _run_staged_process(cmd, staged_repo, timeout)


def _python_tool_command(module: str, args: list[str]) -> list[str]:
    return [sys.executable, "-m", module, *args]


def validate_candidate_set(repo_path: str, files: list[dict], timeout: int = 60) -> dict:
    """Validate proposed Python files together in a disposable repository copy."""
    if not files:
        return {
            "all_pass": False,
            "lint_pass": False,
            "tests_pass": False,
            "message": "No candidate files were supplied.",
        }

    with _stage_tempdir(repo_path) as temp_dir:
        staged_repo = os.path.join(temp_dir, "repo")
        try:
            _copy_workspace(repo_path, staged_repo)
        except (OSError, ValueError, shutil.Error) as exc:
            return {
                "all_pass": False,
                "lint_pass": False,
                "tests_pass": False,
                "message": f"Could not create isolated staging workspace: {exc}",
            }

        ok, message, staged_paths = _stage_candidates(staged_repo, files)
        if not ok:
            return {"all_pass": False, "lint_pass": False, "tests_pass": False, "message": message}

        lint_result, lint_error = _run_staged_process(
            _python_tool_command("ruff", ["check", *staged_paths]), staged_repo, min(timeout, 30)
        )
        if lint_error:
            return {
                "all_pass": False,
                "lint_pass": False,
                "tests_pass": False,
                "message": (
                    "Ruff is unavailable for staged validation. Install Locdex development/validation "
                    f"tools with `python -m pip install -e '.[dev]'`. Details: {lint_error}"
                ),
            }
        if lint_result and lint_result.returncode != 0:
            output = (lint_result.stdout + "\n" + lint_result.stderr).strip()
            return {
                "all_pass": False,
                "lint_pass": False,
                "tests_pass": False,
                "message": f"Ruff failed:\n{output[-12000:]}",
            }

        test_result, test_error = _run_staged_process(
            _python_tool_command("pytest", ["-q"]), staged_repo, timeout
        )
        if test_error:
            return {
                "all_pass": False,
                "lint_pass": True,
                "tests_pass": False,
                "message": (
                    "Pytest is unavailable for staged validation. Install the project's test dependencies "
                    f"or Locdex dev tools. Details: {test_error}"
                ),
            }
        if test_result and test_result.returncode != 0:
            output = (test_result.stdout + "\n" + test_result.stderr).strip()
            return {
                "all_pass": False,
                "lint_pass": True,
                "tests_pass": False,
                "message": f"Tests failed against the proposed files:\n{output[-12000:]}",
            }

        return {
            "all_pass": True,
            "lint_pass": True,
            "tests_pass": True,
            "message": "Candidate passed syntax, security review, Ruff, and tests in a disposable staged workspace.",
        }


def full_validation(repo_path: str, code: str, filepath: str) -> dict:
    """Backward-compatible single-file validation wrapper."""
    return validate_candidate_set(repo_path, [{"filepath": filepath, "code": code}])
