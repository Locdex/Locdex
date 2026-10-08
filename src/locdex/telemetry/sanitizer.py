from __future__ import annotations

import math
import re
from dataclasses import fields

from .schema import RoutingTelemetryEvent

ALLOWED_FIELDS = {field.name for field in fields(RoutingTelemetryEvent)}
STRING_FIELDS = {
    "event", "router_version", "task_class", "language", "repo_size_bucket",
    "requested_change", "complexity_bucket", "tool_intensity_bucket",
    "model_id", "backend", "os", "ram_bucket", "accelerator_class",
    "selected_model", "selection_reason_code", "route", "router_mode",
}
OPTIONAL_STRINGS = {"quant", "prediction_gap_bucket", "fallback_model"}
BOOLEAN_FIELDS = {
    "has_tests", "has_stacktrace", "escalated", "user_reverted",
}
OPTIONAL_BOOLEANS = {
    "compile_passed", "tests_passed", "lint_passed", "validator_passed",
}
INTEGER_FIELDS = {
    "estimated_files", "dependency_fanout", "context_tokens",
    "tool_calls", "edit_attempts",
}
OPTIONAL_INTEGERS = {"input_tokens", "output_tokens"}
OPTIONAL_FLOATS = {
    "latency_ms", "predicted_success_selected", "cost_usd",
}
ENUMS = {
    "event": {"routing_outcome"},
    "task_class": {
        "architecture", "debugging", "testing", "refactor", "bug_fix",
        "repo_navigation", "code_explanation", "tool_heavy",
        "code_generation", "small_edit", "other",
    },
    "language": {"python", "typescript_javascript", "go", "rust", "unknown"},
    "repo_size_bucket": {"small", "medium", "large"},
    "requested_change": {"multi_file", "single_file_or_unknown"},
    "complexity_bucket": {"low", "medium", "high"},
    "tool_intensity_bucket": {"low", "medium", "high"},
    "backend": {"local", "cloud"},
    "os": {"windows", "linux", "darwin", "unknown"},
    "ram_bucket": {"unknown", "lt12", "16gb_class", "24gb_class", "32gb_class", "64gb_plus"},
    "prediction_gap_bucket": {"tight", "close", "clear"},
    "route": {"local", "cloud"},
    "router_mode": {"local_only", "balanced", "fast", "quality"},
}
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}$")
SAFE_REASON = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def sanitize_event(event: dict) -> dict:
    if not isinstance(event, dict):
        raise ValueError("Telemetry event must be a mapping.")
    keys = set(event)
    if keys != ALLOWED_FIELDS:
        raise ValueError(
            "Telemetry schema mismatch; missing or unknown fields: "
            + ", ".join(sorted(keys ^ ALLOWED_FIELDS))
        )

    for field in STRING_FIELDS | OPTIONAL_STRINGS:
        value = event[field]
        if field in OPTIONAL_STRINGS and value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"Invalid telemetry string: {field}")
        if field in ENUMS:
            if value not in ENUMS[field]:
                raise ValueError(f"Invalid telemetry category: {field}")
        elif field == "selection_reason_code":
            if not SAFE_REASON.fullmatch(value):
                raise ValueError("Invalid telemetry reason code.")
        elif not SAFE_IDENTIFIER.fullmatch(value) or "://" in value or ".." in value or re.match(r"^[A-Za-z]:/", value):
            raise ValueError(f"Unsafe telemetry identifier: {field}")

    for field in BOOLEAN_FIELDS | OPTIONAL_BOOLEANS:
        value = event[field]
        if value is None and field in OPTIONAL_BOOLEANS:
            continue
        if not isinstance(value, bool):
            raise ValueError(f"Invalid telemetry boolean: {field}")

    for field in INTEGER_FIELDS | OPTIONAL_INTEGERS:
        value = event[field]
        if value is None and field in OPTIONAL_INTEGERS:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000_000:
            raise ValueError(f"Invalid telemetry count: {field}")

    for field in OPTIONAL_FLOATS:
        value = event[field]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"Invalid telemetry number: {field}")
        if not math.isfinite(value) or value < 0 or value > 10_000_000:
            raise ValueError(f"Out-of-range telemetry number: {field}")
        if field == "predicted_success_selected" and value > 1:
            raise ValueError("Predicted success must be between 0 and 1.")

    return dict(event)


def sanitize_batch(events: list, *, max_events: int = 25) -> list[dict]:
    if not isinstance(events, list) or not events:
        raise ValueError("Telemetry batch must contain at least one event.")
    if len(events) > max_events:
        raise ValueError(f"Telemetry batch exceeds {max_events} events.")
    return [sanitize_event(event) for event in events]
