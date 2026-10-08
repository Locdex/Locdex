from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models.profiles import MODEL_PROFILES

# A qualification probe is not a full LocdexBench score.
# Publish only explicit, vetted fields; never raw hardware diagnostics,
# environment variables, paths, prompts, source code, or model responses.
STATES = {
    "passed", "passed_prompt_only", "prompt_failed", "prompt_mismatch",
    "agent_failed", "agent_probe_failed", "skipped_hardware",
    "model_not_installed", "runtime_unhealthy",
}
ALLOWED_KEYS = {
    "schema_version", "suite", "model", "status", "hardware_tier",
    "backend", "prompt_passed", "prompt_seconds", "agent_passed",
    "agent_seconds", "agent_steps", "tests_unchanged", "verification_passed",
}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def _seconds(raw: Any) -> float | None:
    if isinstance(raw, (float, int)) and not isinstance(raw, bool):
        if 0 <= float(raw) < 1_000_000:
            return round(float(raw), 3)
    return None


def sanitize_qualification(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("Qualification report must be a JSON object.")
    model = str(report.get("model", ""))
    status = str(report.get("status", ""))
    if model not in MODEL_PROFILES:
        raise ValueError("Unknown built-in model profile.")
    if status not in STATES:
        raise ValueError("Unknown qualification status.")
    prompt = report.get("prompt_probe") or {}
    agent = report.get("agent_probe") or {}
    if not isinstance(prompt, dict) or not isinstance(agent, dict):
        raise ValueError("Qualification probe format is invalid.")
    runtime = report.get("runtime") or {}
    if not isinstance(runtime, dict):
        raise ValueError("Runtime format is invalid.")
    backend = str(runtime.get("active_backend") or "unknown")
    if backend not in {"cpu", "cuda", "metal", "unknown"}:
        backend = "unknown"
    safe = {
        "schema_version": 1,
        "suite": "locdex-qualification-v1",
        "model": model,
        "status": status,
        "hardware_tier": MODEL_PROFILES[model].hardware_tier,
        "backend": backend,
        "prompt_passed": prompt.get("passed") if isinstance(prompt.get("passed"), bool) else None,
        "prompt_seconds": _seconds(prompt.get("elapsed_seconds")),
        "agent_passed": agent.get("passed") if isinstance(agent.get("passed"), bool) else None,
        "agent_seconds": _seconds(agent.get("elapsed_seconds")),
        "agent_steps": (
            agent.get("steps")
            if isinstance(agent.get("steps"), int)
            and not isinstance(agent.get("steps"), bool)
            and 0 <= agent["steps"] <= 20
            else None
        ),
        "tests_unchanged": (
            agent.get("tests_unchanged")
            if isinstance(agent.get("tests_unchanged"), bool) else None
        ),
        "verification_passed": (
            agent.get("verification", {}).get("passed")
            if isinstance(agent.get("verification"), dict)
            and isinstance(agent["verification"].get("passed"), bool)
            else None
        ),
    }
    validate_public_record(safe)
    return safe


def validate_public_record(row: dict[str, Any]) -> None:
    if not isinstance(row, dict) or set(row) != ALLOWED_KEYS:
        raise ValueError("Public qualification record contains missing or extra fields.")
    if row.get("schema_version") != 1 or row.get("suite") != "locdex-qualification-v1":
        raise ValueError("Unsupported benchmark publication schema.")
    if row.get("model") not in MODEL_PROFILES or row.get("status") not in STATES:
        raise ValueError("Invalid model or qualification status.")
    if row.get("hardware_tier") != MODEL_PROFILES[row["model"]].hardware_tier:
        raise ValueError("Invalid hardware tier.")
    if row.get("backend") not in {"cpu", "cuda", "metal", "unknown"}:
        raise ValueError("Invalid backend.")
    for name in ("prompt_passed", "agent_passed", "tests_unchanged", "verification_passed"):
        if row[name] is not None and not isinstance(row[name], bool):
            raise ValueError(f"Invalid qualification boolean: {name}.")
    for name in ("prompt_seconds", "agent_seconds"):
        value = row[name]
        if value is not None and _seconds(value) is None:
            raise ValueError(f"Invalid qualification timing: {name}.")
    steps = row["agent_steps"]
    if steps is not None and (
        isinstance(steps, bool) or not isinstance(steps, int) or not 0 <= steps <= 20
    ):
        raise ValueError("Invalid agent step count.")


def export_qualification(input_path: str, output_path: str) -> dict[str, Any]:
    report = json.loads(Path(input_path).read_text(encoding="utf-8"))
    record = sanitize_qualification(report)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"saved": str(output), "suite": record["suite"], "model": record["model"], "status": record["status"]}


def summarize_directory(directory: str) -> dict[str, Any]:
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("Benchmark results directory does not exist.")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        validate_public_record(item)
        rows.append(item)
    by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        model = row["model"]
        aggregate = by_model.setdefault(model, {"runs": 0, "prompt_passes": 0, "agent_passes": 0, "agent_attempts": 0})
        aggregate["runs"] += 1
        aggregate["prompt_passes"] += int(row["prompt_passed"] is True)
        if row["agent_passed"] is not None:
            aggregate["agent_attempts"] += 1
            aggregate["agent_passes"] += int(row["agent_passed"] is True)
    return {
        "suite": "locdex-qualification-v1",
        "records": len(rows),
        "models": by_model,
        "note": "Qualification smoke-probes only; not a general coding benchmark or comparative leaderboard.",
    }
