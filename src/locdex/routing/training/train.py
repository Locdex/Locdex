from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .features import FEATURE_SCHEMA_VERSION
from .labels import success_label


def training_contract():
    return {
        "input": "sanitized RoutingTelemetryEvent rows",
        "output": "versioned local lookup router artifact",
        "online_training": False,
        "raw_prompts_or_code": False,
    }


def _load_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if source.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("events", [])
        if not isinstance(payload, list):
            raise ValueError("Training JSON must be a list or contain an events list.")
        return [row for row in payload if isinstance(row, dict)]

    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _row_success(row: dict[str, Any]) -> bool:
    return success_label(
        compile_passed=row.get("compile_passed"),
        tests_passed=row.get("tests_passed"),
        lint_passed=row.get("lint_passed"),
        validator_passed=row.get("validator_passed"),
        escalated=bool(row.get("escalated")),
        reverted=bool(row.get("user_reverted")),
    )


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {}
    latencies = [
        float(row["latency_ms"])
        for row in rows
        if row.get("latency_ms") is not None
    ]
    costs = [
        float(row.get("cost_usd") or 0.0)
        for row in rows
    ]
    attempts = [
        max(1.0, float(row.get("edit_attempts") or 0) + 1.0)
        for row in rows
    ]
    return {
        "samples": float(len(rows)),
        "success_rate": sum(_row_success(row) for row in rows) / len(rows),
        "avg_cost": sum(costs) / len(costs),
        "avg_latency_ms": (
            sum(latencies) / len(latencies)
            if latencies
            else 0.0
        ),
        "avg_attempts": sum(attempts) / len(attempts),
    }


def build_lookup_artifact(
    rows: list[dict[str, Any]],
    *,
    version: str | None = None,
) -> dict[str, Any]:
    accepted = [
        row
        for row in rows
        if row.get("event") == "routing_outcome"
        and row.get("model_id")
        and row.get("task_class")
    ]
    by_task: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in accepted:
        task_class = str(row["task_class"])
        model_id = str(row["model_id"])
        by_task[task_class][model_id].append(row)
        by_model[model_id].append(row)

    table = {
        task_class: {
            model_id: _aggregate(group)
            for model_id, group in models.items()
        }
        for task_class, models in by_task.items()
    }
    global_models = {
        model_id: _aggregate(group)
        for model_id, group in by_model.items()
    }
    created = datetime.now(timezone.utc)
    return {
        "version": version or created.strftime("%Y%m%d%H%M%S"),
        "kind": "lookup-v1",
        "feature_schema": FEATURE_SCHEMA_VERSION,
        "model_profiles_version": "1",
        "created_at": created.isoformat(),
        "samples": len(accepted),
        "table": table,
        "global_models": global_models,
    }


def train_lookup_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    version: str | None = None,
) -> dict[str, Any]:
    rows = _load_rows(input_path)
    artifact = build_lookup_artifact(rows, version=version)
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(artifact, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "output": str(destination),
        "version": artifact["version"],
        "samples": artifact["samples"],
        "models": sorted(artifact["global_models"]),
        "task_classes": sorted(artifact["table"]),
    }
