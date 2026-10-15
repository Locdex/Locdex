"""Validate pinned, project-owned LocdexBench controls without model inference.

Only a reviewed built-in fixture is executed here. This tool is not the
isolated runner for untrusted agent edits or third-party repositories.
"""
from __future__ import annotations

import json
from pathlib import Path

from locdex.benchmark.controls import validate_controls
from locdex.benchmark.manifest import load_suite

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    tasks = load_suite(ROOT / "benchmarks" / "tasks")
    results: list[dict[str, object]] = []
    for task in tasks:
        outcome = validate_controls(task, ROOT)
        result = {
            "task_id": task.id,
            "pinned_commit": task.base_commit,
            "baseline_visible_failed": outcome.baseline_visible_failed,
            "baseline_hidden_failed": outcome.baseline_hidden_failed,
            "reference_visible_passed": outcome.reference_visible_passed,
            "reference_hidden_passed": outcome.reference_hidden_passed,
            "negative_control_rejected": outcome.negative_control_rejected,
            "passed": outcome.passed,
        }
        results.append(result)
    print(json.dumps({"suite": "locdexbench-v0", "controls": results}, indent=2))
    return 0 if results and all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
