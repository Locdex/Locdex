"""Ground-truth controls for Locdex-owned benchmark fixtures.

This is a trusted fixture validation utility, NOT a general agent runner.
Only the reviewed built-in fixture can be executed on a CI host. Unknown
or third-party benchmark code must use an isolated containerized runner.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .manifest import ManifestError, TaskManifest, verify_pinned_fixture


APPROVED_FIXTURES = frozenset({"py-arithmetic-edge-001"})


@dataclass(frozen=True)
class ControlOutcome:
    baseline_visible_failed: bool
    baseline_hidden_failed: bool
    reference_visible_passed: bool
    reference_hidden_passed: bool
    negative_control_rejected: bool

    @property
    def passed(self) -> bool:
        return all((
            self.baseline_visible_failed, self.baseline_hidden_failed,
            self.reference_visible_passed, self.reference_hidden_passed,
            self.negative_control_rejected,
        ))


def _run_suite(workspace: Path, tests: Path, *, hidden: bool) -> bool:
    if hidden:
        args = [sys.executable, "-m", "unittest", "discover", "-s",
                str(tests.parent), "-p", tests.name]
    else:
        args = [sys.executable, "-m", "unittest", "discover", "-s",
                "tests", "-p", "test_visible.py"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run = subprocess.run(
        args, cwd=workspace, env=env, capture_output=True,
        text=True, check=False, timeout=30,
    )
    return run.returncode == 0


def _copy_fixture(task: TaskManifest, root: Path, target: Path) -> None:
    shutil.copytree(root / task.fixture, target, symlinks=False)


def validate_controls(task: TaskManifest, repo_root: str | Path) -> ControlOutcome:
    """Validate an audited fixture with baseline, reference and negative controls.

    CAUTION: executes fixture-authored Python on the host. Never call this
    on unreviewed tasks or model-generated code; use a locked-down container.
    """
    if task.id not in APPROVED_FIXTURES:
        raise ManifestError("Host fixture-control validation is restricted to audited built-in tasks.")
    root = Path(repo_root).resolve()
    verify_pinned_fixture(task, root)
    hidden = root / task.hidden_grader
    with tempfile.TemporaryDirectory(prefix="locdexbench-controls-") as temp:
        base = Path(temp)
        baseline = base / "baseline"
        _copy_fixture(task, root, baseline)
        b_visible = not _run_suite(baseline, hidden, hidden=False)
        b_hidden = not _run_suite(baseline, hidden, hidden=True)

        reference = base / "reference"
        _copy_fixture(task, root, reference)
        shutil.copyfile(root / task.reference_file, reference / "core.py")
        r_visible = _run_suite(reference, hidden, hidden=False)
        r_hidden = _run_suite(reference, hidden, hidden=True)

        incorrect = base / "incorrect"
        _copy_fixture(task, root, incorrect)
        shutil.copyfile(root / task.negative_file, incorrect / "core.py")
        n_rejected = (
            not _run_suite(incorrect, hidden, hidden=False)
            and not _run_suite(incorrect, hidden, hidden=True)
        )
    return ControlOutcome(b_visible, b_hidden, r_visible, r_hidden, n_rejected)


def validate_agent_changes(
    task: TaskManifest,
    before: str | Path,
    after: str | Path,
) -> None:
    """Reject edits to any fixture file outside the manifest's write scope."""
    initial, final = Path(before), Path(after)
    for directory in (initial, final):
        if not directory.is_dir():
            raise ManifestError("Missing workspace.")
        if any(p.is_symlink() for p in directory.rglob("*")):
            raise ManifestError("Symlinks are not allowed in benchmark workspaces.")
    def files(directory: Path) -> dict[str, bytes]:
        return {
            p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(directory).parts
        }
    original = files(initial)
    updated = files(final)
    changed = {
        path for path in original.keys() | updated.keys()
        if original.get(path) != updated.get(path)
    }
    forbidden = changed - set(task.allowed_writes)
    if forbidden:
        raise ManifestError(f"Agent modified protected files: {sorted(forbidden)}")
