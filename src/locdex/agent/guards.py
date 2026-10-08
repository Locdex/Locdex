from __future__ import annotations

from pathlib import Path
import re
from typing import Any


IGNORED_STATUS_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


_CHANGE_VERBS = (
    "add",
    "write",
    "create",
    "update",
    "modify",
    "change",
    "fix",
    "refactor",
    "rename",
    "remove",
    "delete",
)


def is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    name = Path(normalized).name
    parts = set(Path(normalized).parts)
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts
        or "test" in parts
    )


def task_explicitly_allows_test_changes(task: str, path: str | None = None) -> bool:
    text = " ".join(task.lower().split())
    verbs = "|".join(_CHANGE_VERBS)
    qualifiers = (
        r"(?:(?:the|these|those|failing|broken|unit|integration|regression|"
        r"existing|current|new)\s+){0,4}"
    )
    if re.search(
        rf"\b(?:{verbs})\b\s+{qualifiers}\btests?\b",
        text,
    ):
        return True

    if path:
        normalized = path.replace("\\", "/").lower()
        basename = re.escape(Path(normalized).name)
        if re.search(
            rf"\b(?:{verbs})\b\s+(?:(?:the|file)\s+)?{basename}\b",
            text,
        ):
            return True
    return False


def task_explicitly_names_change(task: str, path: str) -> bool:
    text = " ".join(task.lower().split())
    normalized = path.replace("\\", "/").lower()
    basename = Path(normalized).name
    if normalized not in text and basename not in text:
        return False
    return any(re.search(rf"\b{verb}\b", text) for verb in _CHANGE_VERBS)


def clean_model_result(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(result)
    if tool_name != "read_file" or not isinstance(cleaned.get("content"), str):
        return cleaned

    raw_lines = str(cleaned["content"]).splitlines()
    output: list[str] = []
    for line in raw_lines:
        prefix, separator, remainder = line.partition(": ")
        output.append(remainder if separator and prefix.isdigit() else line)
    cleaned["content"] = "\n".join(output)
    return cleaned


def preexisting_changed_paths(status_result: dict[str, Any]) -> set[str]:
    output = str(status_result.get("output", ""))
    paths: set[str] = set()
    for line in output.splitlines():
        if not line or line.startswith("##"):
            continue
        candidate = line[3:].strip() if len(line) >= 4 else ""
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1].strip()
        if not candidate:
            continue
        normalized = candidate.replace("\\", "/")
        if set(normalized.split("/")) & IGNORED_STATUS_PARTS:
            continue
        paths.add(normalized)
    return paths


def snapshot_file(
    repo_path: str,
    tool_name: str,
    args: dict[str, Any],
    mutating_tools: set[str],
) -> tuple[Path, bytes | None] | None:
    if tool_name not in mutating_tools:
        return None

    raw_path = args.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None

    root = Path(repo_path).resolve()
    candidate = (root / raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    if candidate.is_file():
        try:
            return candidate, candidate.read_bytes()
        except OSError:
            return None
    return candidate, None


def restore_snapshot(snapshot: tuple[Path, bytes | None] | None) -> None:
    if snapshot is None:
        return
    path, previous = snapshot
    try:
        if previous is None:
            if path.is_file():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(previous)
    except OSError:
        return


def guard_mutation_result(
    repo_path: str,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    snapshot: tuple[Path, bytes | None] | None,
) -> dict[str, Any]:
    if "error" in result or result.get("ok") is not True:
        return result

    if tool_name == "write_file" and snapshot is not None:
        _, previous = snapshot
        if previous is not None and not bool(args.get("overwrite", False)):
            restore_snapshot(snapshot)
            return {
                "error": (
                    "write_file overwrite was rolled back. Existing files require "
                    "overwrite=true; prefer replace_in_file for scoped edits."
                ),
                "rolled_back": True,
                "path": str(args.get("path", "")),
            }

    path_text = result.get("path") or args.get("path")
    if not isinstance(path_text, str) or not path_text.lower().endswith((".py", ".pyi")):
        return result

    root = Path(repo_path).resolve()
    candidate = (root / path_text).resolve()
    try:
        source = candidate.read_text(encoding="utf-8")
        compile(source, str(candidate), "exec")
    except (OSError, UnicodeDecodeError):
        return result
    except SyntaxError as exc:
        restore_snapshot(snapshot)
        location = f"line {exc.lineno}" if exc.lineno else "unknown line"
        return {
            "error": (
                f"Invalid Python edit was rolled back: {exc.msg} ({location}). "
                "Inspect the raw source and make a smaller exact replacement."
            ),
            "rolled_back": True,
            "path": path_text,
        }

    return result
