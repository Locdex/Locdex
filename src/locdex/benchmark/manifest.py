"""Strict LocdexBench v0 task manifests: data only, never executable instructions."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


class ManifestError(ValueError):
    """A benchmark task is malformed, unsafe, or not pinned to its fixture."""


TASK_FIELDS = {
    "suite", "id", "category", "language", "license", "fixture",
    "base_commit", "task", "visible_checks", "hidden_grader",
    "reference_file", "negative_file", "allowed_writes", "limits",
}
LIMIT_FIELDS = {"wall_seconds", "model_steps", "max_output_tokens", "max_context_tokens", "network"}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{4,79}$")
COMMIT = re.compile(r"^[a-f0-9]{40}$")
VISIBLE_CHECK = ("python", "-m", "unittest", "discover", "-s", "tests", "-p", "test_visible.py")


def _object(raw: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != fields:
        missing = fields - set(raw) if isinstance(raw, dict) else fields
        extra = set(raw) - fields if isinstance(raw, dict) else set()
        raise ManifestError(f"{name}: invalid fields (missing={sorted(missing)}, extra={sorted(extra)}).")
    return raw


def _path(value: Any, *, prefix: str | None = None) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ManifestError("Path must be a non-empty repository-relative string.")
    if "\\" in value or ":" in value or value.startswith("/") or "//" in value:
        raise ManifestError("Backslashes, absolute paths and drive paths are forbidden.")
    p = PurePosixPath(value)
    if any(part in ("", ".", "..") for part in value.split("/")) or p.is_absolute():
        raise ManifestError("Path traversal and dot segments are forbidden.")
    if prefix and not value.startswith(prefix + "/"):
        raise ManifestError(f"Expected path beneath {prefix}/.")
    return value


def _positive_integer(value: Any, maximum: int, name: str) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ManifestError(f"{name} must be an integer in [1, {maximum}].")
    return value


@dataclass(frozen=True)
class TaskManifest:
    suite: str
    id: str
    category: str
    language: str
    license: str
    fixture: str
    base_commit: str
    task: str
    visible_checks: tuple[tuple[str, ...], ...]
    hidden_grader: str
    reference_file: str
    negative_file: str
    allowed_writes: tuple[str, ...]
    limits: dict[str, int | bool]


def parse_manifest(raw: Any) -> TaskManifest:
    row = _object(raw, TASK_FIELDS, "Task")
    if row["suite"] != "locdexbench-v0":
        raise ManifestError("Unsupported LocdexBench schema.")
    if not isinstance(row["id"], str) or not IDENTIFIER.fullmatch(row["id"]):
        raise ManifestError("Invalid task identifier.")
    if row["category"] != "bugfix" or row["language"] != "python":
        raise ManifestError("This v0 implementation supports Python bugfix tasks only.")
    if row["license"] not in ("MIT", "Apache-2.0", "BSD-3-Clause"):
        raise ManifestError("Unsupported fixture license.")
    if not isinstance(row["base_commit"], str) or not COMMIT.fullmatch(row["base_commit"]):
        raise ManifestError("base_commit must be a full 40-character Git SHA.")
    fixture = _path(row["fixture"], prefix="benchmarks/fixtures")
    grader = _path(row["hidden_grader"], prefix="benchmarks/graders")
    reference = _path(row["reference_file"], prefix="benchmarks/references")
    negative = _path(row["negative_file"], prefix="benchmarks/references")
    if not all(row["id"] in path for path in (fixture, grader, reference, negative)):
        raise ManifestError("Fixture, grader and control paths must match the task ID.")
    if grader.startswith(fixture + "/") or reference.startswith(fixture + "/"):
        raise ManifestError("Grader and controls must remain outside the agent workspace.")
    task = row["task"]
    if not isinstance(task, str) or not 12 <= len(task) <= 1000:
        raise ManifestError("Task description must contain 12-1000 characters.")
    if not isinstance(row["visible_checks"], list) or row["visible_checks"] != [list(VISIBLE_CHECK)]:
        raise ManifestError("This pilot only permits the fixed Python unittest visible-check command.")
    writes = row["allowed_writes"]
    if not isinstance(writes, list) or writes != ["core.py"]:
        raise ManifestError("Pilot agent write scope must be exactly ['core.py'].")
    limits = _object(row["limits"], LIMIT_FIELDS, "Limits")
    cleaned_limits = {
        "wall_seconds": _positive_integer(limits["wall_seconds"], 1800, "wall_seconds"),
        "model_steps": _positive_integer(limits["model_steps"], 32, "model_steps"),
        "max_output_tokens": _positive_integer(limits["max_output_tokens"], 8192, "max_output_tokens"),
        "max_context_tokens": _positive_integer(limits["max_context_tokens"], 65536, "max_context_tokens"),
    }
    if limits["network"] is not False:
        raise ManifestError("The local-only pilot must disable network access.")
    cleaned_limits["network"] = False
    return TaskManifest(
        suite=row["suite"], id=row["id"], category=row["category"],
        language=row["language"], license=row["license"], fixture=fixture,
        base_commit=row["base_commit"], task=task,
        visible_checks=(VISIBLE_CHECK,), hidden_grader=grader,
        reference_file=reference, negative_file=negative,
        allowed_writes=("core.py",), limits=cleaned_limits,
    )


def load_manifest(filename: str | Path) -> TaskManifest:
    path = Path(filename)
    if path.stat().st_size > 32_000:
        raise ManifestError("Task manifest exceeds the size limit.")
    try:
        return parse_manifest(yaml.safe_load(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        raise ManifestError("Unable to parse benchmark YAML.") from exc


def load_suite(directory: str | Path) -> list[TaskManifest]:
    root = Path(directory)
    tasks = [load_manifest(path) for path in sorted(root.glob("*.yaml"))]
    if not tasks:
        raise ManifestError("No benchmark manifests found.")
    if len(set(row.id for row in tasks)) != len(tasks):
        raise ManifestError("Duplicate task identifiers in benchmark suite.")
    return tasks


def verify_pinned_fixture(task: TaskManifest, repo_root: str | Path) -> None:
    """Check the bundled fixture exactly matches the *committed* Git snapshot."""
    root = Path(repo_root).resolve()
    completed = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-t", task.base_commit],
        capture_output=True, text=True, check=False, timeout=15,
    )
    if completed.returncode or completed.stdout.strip() != "commit":
        raise ManifestError("Pinned fixture commit is unavailable; fetch full history.")
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only",
         task.base_commit, "--", task.fixture],
        capture_output=True, text=True, check=False, timeout=15,
    )
    if listing.returncode:
        raise ManifestError("Cannot inspect pinned fixture tree.")
    expected = sorted(line for line in listing.stdout.splitlines() if line)
    actual = sorted(
        p.relative_to(root).as_posix()
        for p in (root / task.fixture).rglob("*") if p.is_file()
    )
    if not expected or actual != expected:
        raise ManifestError("Fixture file set differs from pinned commit.")
    for path in expected:
        file = root / path
        if file.is_symlink() or not file.resolve().is_relative_to(root / task.fixture):
            raise ManifestError("Unsafe fixture symlink or path.")
        original = subprocess.run(
            ["git", "-C", str(root), "show", f"{task.base_commit}:{path}"],
            capture_output=True, check=False, timeout=15,
        )
        if original.returncode or file.read_bytes() != original.stdout:
            raise ManifestError(f"Fixture contents differ from pinned commit: {path}")
    for path in (task.hidden_grader, task.reference_file, task.negative_file):
        target = root / path
        if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ManifestError("Missing or unsafe external grader/reference file.")
