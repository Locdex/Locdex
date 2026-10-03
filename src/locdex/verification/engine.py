from __future__ import annotations

import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from ..tools.executor import run_command, run_tests


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    status: str
    command: str | None = None
    output: str = ""

    @property
    def passed(self) -> bool:
        return self.status in {"passed", "skipped"}


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: tuple[VerificationCheck, ...] = ()

    @property
    def failures(self) -> tuple[VerificationCheck, ...]:
        return tuple(check for check in self.checks if check.status == "failed")

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
            "failures": [asdict(check) for check in self.failures],
        }


class VerificationEngine:
    def __init__(self, *, run_lint: bool = True):
        self.run_lint = run_lint

    @staticmethod
    def _changed_existing_files(repo_path: str, changed_files: list[str] | tuple[str, ...]) -> list[str]:
        root = Path(repo_path).resolve()
        result: list[str] = []
        for relative in changed_files:
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if candidate.is_file():
                result.append(str(candidate.relative_to(root)).replace("\\", "/"))
        return sorted(set(result))

    @staticmethod
    def _from_tool_result(name: str, result: dict, *, skipped_message: str | None = None) -> VerificationCheck:
        if result.get("returncode") is None and skipped_message:
            return VerificationCheck(name, "skipped", output=skipped_message)

        command = result.get("command")
        output = str(result.get("output", ""))
        return VerificationCheck(
            name=name,
            status="passed" if result.get("ok") is True else "failed",
            command=str(command) if command else None,
            output=output,
        )

    def _compile_python(self, repo_path: str, changed_files: list[str]) -> VerificationCheck:
        python_files = [path for path in changed_files if path.lower().endswith(".py")]
        if not python_files:
            return VerificationCheck("compile", "skipped", output="No changed Python files.")

        result = run_command(
            repo_path,
            [sys.executable, "-m", "py_compile", *python_files],
            timeout=120,
        )
        return self._from_tool_result("compile", result)

    def _tests(self, repo_path: str) -> VerificationCheck:
        result = run_tests(repo_path)
        if (
            result.get("returncode") is None
            and "No supported test runner" in str(result.get("output", ""))
        ):
            return VerificationCheck("tests", "skipped", output=str(result.get("output", "")))
        return self._from_tool_result("tests", result)

    @staticmethod
    def _repo_uses_ruff(repo_path: str) -> bool:
        root = Path(repo_path).resolve()
        if (root / "ruff.toml").is_file() or (root / ".ruff.toml").is_file():
            return True
        pyproject = root / "pyproject.toml"
        if not pyproject.is_file():
            return False
        try:
            return "[tool.ruff" in pyproject.read_text(encoding="utf-8")
        except OSError:
            return False

    def _lint_python(self, repo_path: str, changed_files: list[str]) -> VerificationCheck:
        python_files = [path for path in changed_files if path.lower().endswith(".py")]
        if not python_files:
            return VerificationCheck("lint", "skipped", output="No changed Python files.")

        if not self.run_lint:
            return VerificationCheck("lint", "skipped", output="Lint verification disabled.")

        if not self._repo_uses_ruff(repo_path):
            return VerificationCheck(
                "lint",
                "skipped",
                output="Target repository does not declare Ruff configuration.",
            )

        ruff = shutil.which("ruff")
        if not ruff:
            return VerificationCheck("lint", "skipped", output="Ruff is configured but not installed.")

        result = run_command(repo_path, [ruff, "check", *python_files], timeout=120)
        return self._from_tool_result("lint", result)

    def verify(
        self,
        repo_path: str,
        changed_files: list[str] | tuple[str, ...],
    ) -> VerificationResult:
        existing = self._changed_existing_files(repo_path, changed_files)
        checks = (
            self._compile_python(repo_path, existing),
            self._tests(repo_path),
            self._lint_python(repo_path, existing),
        )
        return VerificationResult(
            passed=all(check.passed for check in checks),
            checks=checks,
        )

    def verify_noop(self) -> VerificationResult:
        check = VerificationCheck("verification", "passed", output="verification pipeline ready")
        return VerificationResult(True, (check,))
