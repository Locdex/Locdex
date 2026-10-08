from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from platformdirs import user_config_dir


def _dir() -> Path:
    return Path(
        os.environ.get(
            "LOCDEX_CONFIG_DIR",
            user_config_dir("locdex", "Locdex"),
        )
    ).expanduser()


def _path() -> Path:
    return _dir() / "telemetry.json"


def load() -> dict:
    try:
        payload = json.loads(_path().read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def mode() -> str:
    override = os.environ.get("LOCDEX_TELEMETRY_MODE")
    settings = load()
    value = (
        override
        if override is not None
        else settings.get("mode", "basic" if settings.get("enabled", True) else "off")
    )
    normalized = str(value).strip().lower()
    return normalized if normalized in {"off", "basic", "research"} else "off"


def enabled() -> bool:
    return mode() in {"basic", "research"}


def set_mode(value: str) -> None:
    normalized = value.strip().lower()
    if normalized not in {"off", "basic", "research"}:
        raise ValueError("telemetry mode must be off, basic, or research")
    data = load()
    data.pop("enabled", None)
    data["mode"] = normalized
    save(data)
    if normalized == "off":
        from .queue import clear

        clear()


def set_enabled(value: bool) -> None:
    set_mode("basic" if value else "off")


def endpoint() -> str:
    return str(
        os.environ.get(
            "LOCDEX_TELEMETRY_ENDPOINT",
            load().get("endpoint", ""),
        )
    ).strip()


def _validate_endpoint(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Telemetry endpoint must use HTTPS.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Telemetry endpoint cannot contain credentials or query parameters.")
    return candidate


def set_endpoint(value: str) -> None:
    data = load()
    data["endpoint"] = _validate_endpoint(value)
    save(data)


def notice_once() -> bool:
    if not enabled():
        return False
    data = load()
    if data.get("notice_shown"):
        return False
    print(
        "Locdex BASIC telemetry is on by default: sanitized task/model/outcome "
        "metrics only; never code, prompts, paths, or account identifiers. "
        "Run 'locdex telemetry preview' to inspect queued data, or "
        "'locdex telemetry disable' to opt out and clear pending metrics."
    )
    if not endpoint():
        print("No telemetry endpoint configured; nothing will be uploaded.")
    data["notice_shown"] = True
    try:
        save(data)
    except OSError:
        pass
    return True
