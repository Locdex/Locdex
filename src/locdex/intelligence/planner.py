from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .graph import build_repository_graph, related_files
from .source import build_task_context

_TASK_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class MissingSymbol:
    name: str
    target_path: str
    target_module: str
    requested_by: str
    requested_by_test: bool
    alias: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_path": self.target_path,
            "target_module": self.target_module,
            "requested_by": self.requested_by,
            "requested_by_test": self.requested_by_test,
            "alias": self.alias,
        }


@dataclass
class RetrievalPlan:
    primary_files: list[dict[str, Any]] = field(default_factory=list)
    required_symbols: list[str] = field(default_factory=list)
    missing_symbols: list[MissingSymbol] = field(default_factory=list)
    exact_ranges: list[dict[str, Any]] = field(default_factory=list)
    related_tests: list[str] = field(default_factory=list)
    likely_change_files: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_files": self.primary_files,
            "required_symbols": self.required_symbols,
            "missing_symbols": [item.to_dict() for item in self.missing_symbols],
            "exact_ranges": self.exact_ranges,
            "related_tests": self.related_tests,
            "likely_change_files": self.likely_change_files,
            "findings": self.findings,
        }

    def to_prompt(self) -> str:
        lines = ["RETRIEVAL PLAN", "", "Primary files:"]
        if self.primary_files:
            for row in self.primary_files:
                reasons = ", ".join(row.get("reasons", []))
                lines.append(f"- {row['path']} | {reasons}")
        else:
            lines.append("- (none)")

        lines.extend(["", "Required symbols:"])
        lines.extend(f"- {name}" for name in self.required_symbols or ["(none)"])

        lines.extend(["", "Missing local symbols:"])
        if self.missing_symbols:
            for item in self.missing_symbols:
                source = "test" if item.requested_by_test else "source"
                lines.append(
                    f"- {item.name} expected in {item.target_path}; "
                    f"requested by {item.requested_by} ({source})"
                )
        else:
            lines.append("- (none detected)")

        lines.extend(["", "Likely change files:"])
        lines.extend(f"- {path}" for path in self.likely_change_files or ["(none)"])

        lines.extend(["", "Related tests:"])
        lines.extend(f"- {path}" for path in self.related_tests or ["(none)"])

        lines.extend(["", "Exact source ranges available:"])
        if self.exact_ranges:
            for row in self.exact_ranges:
                lines.append(
                    f"- {row['path']}:{row['start_line']}-{row['end_line']} | "
                    f"{row['reason']}"
                )
        else:
            lines.append("- (none)")

        lines.extend(["", "Structural findings:"])
        lines.extend(f"- {item}" for item in self.findings or ["(none)"])
        return "\n".join(lines)


def detect_missing_local_imports(root: str) -> list[MissingSymbol]:
    graph = build_repository_graph(root)
    bindings = {
        row["path"]: set(row.get("bindings") or [])
        for row in graph["files"]
    }
    module_paths = {
        str(row["module"]): str(row["path"])
        for row in graph["files"]
        if row.get("module")
    }

    missing: list[MissingSymbol] = []
    seen: set[tuple[str, str, str]] = set()
    for row in graph["files"]:
        for import_row in row["imports"]:
            target_path = str(import_row.get("path") or "")
            if not target_path:
                continue
            target_bindings = bindings.get(target_path, set())
            target_module = str(import_row.get("module") or "")
            for imported in import_row.get("names") or []:
                name = str(imported.get("name") or "")
                if not name or name == "*":
                    continue
                if name in target_bindings:
                    continue
                if target_module and f"{target_module}.{name}" in module_paths:
                    continue
                key = (row["path"], target_path, name)
                if key in seen:
                    continue
                seen.add(key)
                missing.append(
                    MissingSymbol(
                        name=name,
                        target_path=target_path,
                        target_module=str(import_row.get("module") or ""),
                        requested_by=row["path"],
                        requested_by_test=bool(row["is_test"]),
                        alias=str(imported.get("alias") or ""),
                    )
                )

    return sorted(
        missing,
        key=lambda item: (
            not item.requested_by_test,
            item.target_path,
            item.name,
            item.requested_by,
        ),
    )


def plan_retrieval(
    root: str,
    task: str,
    *,
    max_files: int = 8,
    source_tokens: int = 1800,
) -> RetrievalPlan:
    ranked = related_files(root, task, limit=max_files)
    primary_paths = {row["path"] for row in ranked}
    context = build_task_context(
        root,
        task,
        max_tokens=source_tokens,
        max_files=max_files,
    )

    task_tokens = {token.lower() for token in _TASK_TOKEN.findall(task)}
    all_missing = detect_missing_local_imports(root)
    missing = [
        item
        for item in all_missing
        if (
            item.target_path in primary_paths
            or item.requested_by in primary_paths
            or item.name.lower() in task_tokens
        )
    ]

    required_symbols: list[str] = []
    for name in context["task_symbols"]:
        if name not in required_symbols:
            required_symbols.append(name)
    for item in missing:
        if item.name not in required_symbols:
            required_symbols.append(item.name)

    related_tests = sorted(
        {
            row["path"]
            for row in ranked
            if row.get("is_test")
        }
        | {
            item.requested_by
            for item in missing
            if item.requested_by_test
        }
    )

    likely_change: list[str] = []
    for item in missing:
        if item.target_path not in likely_change:
            likely_change.append(item.target_path)
    for row in ranked:
        if row.get("is_test"):
            continue
        reasons = set(row.get("reasons") or [])
        if reasons & {"path/task match", "symbol/task match", "reference/task match"}:
            if row["path"] not in likely_change:
                likely_change.append(row["path"])

    exact_ranges = [
        {
            "path": item["path"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "reason": item["reason"],
            "tokens": item["tokens"],
        }
        for item in context["snippets"]
    ]

    findings: list[str] = []
    for item in missing:
        findings.append(
            f"{item.name} is imported from local module {item.target_module} "
            f"by {item.requested_by}, but {item.target_path} does not define it."
        )

    return RetrievalPlan(
        primary_files=ranked,
        required_symbols=required_symbols,
        missing_symbols=missing,
        exact_ranges=exact_ranges,
        related_tests=related_tests,
        likely_change_files=likely_change,
        findings=findings,
    )


def retrieval_plan_text(
    root: str,
    task: str,
    *,
    max_files: int = 8,
    source_tokens: int = 1800,
) -> str:
    return plan_retrieval(
        root,
        task,
        max_files=max_files,
        source_tokens=source_tokens,
    ).to_prompt()
