from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .config import load_settings, locdex_cache_dir, save_settings, selected_model_key

SCHEMA_VERSION = 1
DEFAULT_TELEMETRY_ENDPOINT = ""  # Set only when the official Locdex collector is deployed.

TASK_CATEGORIES = {
    "bug_fix",
    "feature",
    "refactor",
    "tests",
    "documentation",
    "dependency",
    "configuration",
    "git_operation",
    "code_review",
    "other",
}
LANGUAGES = {"python", "typescript_javascript", "go", "rust", "other", "mixed", "unknown"}
ROUTES = {"local", "cloud", "none"}
ESCALATION_REASONS = {
    "none",
    "local_incomplete",
    "local_runtime_failure",
    "local_requested_escalation",
    "cloud_unavailable",
    "cloud_validation_failure",
    "other",
}

_SAFE_MODEL_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,120}$")


def _aggregate_path() -> Path:
    return locdex_cache_dir() / "telemetry" / "aggregate-v1.json"


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_telemetry_enabled() -> bool:
    """Telemetry is off by default. Environment override wins over saved settings."""
    override = _env_bool("LOCDEX_TELEMETRY")
    if override is not None:
        return override
    return bool(load_settings().get("telemetry_enabled", False))


def set_telemetry_enabled(enabled: bool) -> None:
    settings = load_settings()
    settings["telemetry_enabled"] = bool(enabled)
    save_settings(settings)


def telemetry_endpoint() -> str:
    env = os.environ.get("LOCDEX_TELEMETRY_ENDPOINT")
    if env is not None:
        return env.strip()
    saved = str(load_settings().get("telemetry_endpoint", "")).strip()
    return saved or DEFAULT_TELEMETRY_ENDPOINT


def _period() -> str:
    # Month bucket only. Exact task timestamps are deliberately not collected.
    return datetime.now(timezone.utc).strftime("%Y-%m")


def classify_task_locally(task_text: str) -> str:
    """Map raw task text to one fixed label locally. Raw text is never returned/sent."""
    text = task_text.lower()
    if any(token in text for token in ("commit", "push", "pull", "git ", "stage ")):
        return "git_operation"
    if any(token in text for token in ("test", "pytest", "coverage", "spec")):
        return "tests"
    if any(token in text for token in ("readme", "docs", "documentation", "comment")):
        return "documentation"
    if any(token in text for token in ("dependency", "dependencies", "upgrade package", "update package", "pip install", "npm install")):
        return "dependency"
    if any(token in text for token in ("config", "configuration", "setting", "environment variable", ".env")):
        return "configuration"
    if any(token in text for token in ("review", "audit", "inspect", "explain")):
        return "code_review"
    if any(token in text for token in ("refactor", "rename", "cleanup", "clean up", "restructure")):
        return "refactor"
    if any(token in text for token in ("fix", "bug", "error", "broken", "failing", "failure")):
        return "bug_fix"
    if any(token in text for token in ("add ", "implement", "create", "build", "feature")):
        return "feature"
    return "other"


def detect_workspace_language(repo_path: str = ".") -> str:
    root = Path(repo_path)
    markers = []
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists() or (root / "setup.py").exists():
        markers.append("python")
    if (root / "package.json").exists():
        markers.append("typescript_javascript")
    if (root / "go.mod").exists():
        markers.append("go")
    if (root / "Cargo.toml").exists():
        markers.append("rust")
    if len(markers) > 1:
        return "mixed"
    return markers[0] if markers else "unknown"


def _safe_choice(value: str | None, allowed: set[str], fallback: str) -> str:
    value = (value or "").strip().lower()
    return value if value in allowed else fallback


def _safe_model_label(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value if _SAFE_MODEL_RE.fullmatch(value) else None


def _read_aggregate() -> dict[str, Any]:
    path = _aggregate_path()
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "buckets": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "buckets": {}}
    if not isinstance(data, dict) or not isinstance(data.get("buckets"), dict):
        return {"schema_version": SCHEMA_VERSION, "buckets": {}}
    return data


def _write_aggregate(data: dict[str, Any]) -> None:
    path = _aggregate_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _bucket_dimensions(
    *,
    task_category: str,
    language: str,
    route: str,
    local_model: str | None,
    cloud_provider: str | None,
    cloud_model: str | None,
    escalation_reason: str | None,
) -> dict[str, Any]:
    return {
        "period": _period(),
        "task_category": _safe_choice(task_category, TASK_CATEGORIES, "other"),
        "language": _safe_choice(language, LANGUAGES, "unknown"),
        "route": _safe_choice(route, ROUTES, "none"),
        "local_model": _safe_model_label(local_model),
        "cloud_provider": _safe_model_label(cloud_provider),
        "cloud_model": _safe_model_label(cloud_model),
        "escalation_reason": _safe_choice(escalation_reason, ESCALATION_REASONS, "other"),
    }


def log_routing_outcome(
    task_category: str,
    language: str,
    provider: str,
    success: bool,
    attempts: int,
    *,
    local_model: str | None = None,
    cloud_provider: str | None = None,
    cloud_model: str | None = None,
    escalation_reason: str | None = None,
) -> None:
    """Aggregate one routing outcome locally.

    Backward compatible with the earlier five-argument API. `provider` here means
    route/source (`local`, `cloud`, or `none`), not an API provider name.

    No task text, code, path, repository identifier, machine identifier, or exact
    timestamp is accepted by this function, so those values cannot accidentally be
    serialized into the telemetry payload.
    """
    if not is_telemetry_enabled():
        return

    dims = _bucket_dimensions(
        task_category=task_category,
        language=language,
        route=provider,
        local_model=local_model or selected_model_key(),
        cloud_provider=cloud_provider,
        cloud_model=cloud_model,
        escalation_reason=escalation_reason or "none",
    )
    key = json.dumps(dims, sort_keys=True, separators=(",", ":"))
    data = _read_aggregate()
    bucket = data["buckets"].setdefault(
        key,
        {"dimensions": dims, "runs": 0, "successes": 0, "total_attempts": 0},
    )
    bucket["runs"] = int(bucket.get("runs", 0)) + 1
    bucket["successes"] = int(bucket.get("successes", 0)) + int(bool(success))
    bucket["total_attempts"] = int(bucket.get("total_attempts", 0)) + max(0, min(int(attempts), 50))
    _write_aggregate(data)


def get_aggregated_stats() -> dict:
    """Backward-compatible local stats used for analysis/testing."""
    stats: dict[tuple[str, str], dict[str, int]] = {}
    for bucket in _read_aggregate().get("buckets", {}).values():
        dims = bucket.get("dimensions", {})
        key = (str(dims.get("language", "unknown")), str(dims.get("task_category", "other")))
        item = stats.setdefault(key, {"attempts": 0, "successes": 0, "runs": 0})
        item["attempts"] += int(bucket.get("total_attempts", 0))
        item["successes"] += int(bucket.get("successes", 0))
        item["runs"] += int(bucket.get("runs", 0))
    return stats


def telemetry_preview() -> dict[str, Any]:
    """Return exactly the shape that would be uploaded, with no network call."""
    buckets = [bucket for bucket in _read_aggregate().get("buckets", {}).values()]
    return {
        "schema_version": SCHEMA_VERSION,
        "product": "locdex",
        "aggregates": buckets,
    }


def clear_local_telemetry() -> None:
    try:
        _aggregate_path().unlink()
    except FileNotFoundError:
        pass


def flush_telemetry(timeout: float = 3.0) -> dict[str, Any]:
    """Upload aggregate buckets only when explicitly enabled and an endpoint exists.

    There is deliberately no per-install/user identifier. A network service may still
    observe transport metadata such as an IP address unless the collector/proxy is
    configured not to retain it; that is a backend privacy requirement, not something
    the client can guarantee by itself.
    """
    if not is_telemetry_enabled():
        return {"sent": False, "reason": "disabled"}
    endpoint = telemetry_endpoint()
    if not endpoint:
        return {"sent": False, "reason": "no_endpoint"}

    payload = telemetry_preview()
    if not payload["aggregates"]:
        return {"sent": False, "reason": "empty"}

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "locdex-telemetry/1"},
            timeout=max(0.5, min(float(timeout), 10.0)),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"sent": False, "reason": "network_error", "error": str(exc)}

    count = sum(int(item.get("runs", 0)) for item in payload["aggregates"])
    clear_local_telemetry()
    return {"sent": True, "runs": count, "buckets": len(payload["aggregates"])}


def telemetry_status() -> dict[str, Any]:
    preview = telemetry_preview()
    return {
        "enabled": is_telemetry_enabled(),
        "endpoint_configured": bool(telemetry_endpoint()),
        "aggregate_path": str(_aggregate_path()),
        "queued_buckets": len(preview["aggregates"]),
        "queued_runs": sum(int(item.get("runs", 0)) for item in preview["aggregates"]),
        "schema_version": SCHEMA_VERSION,
    }
