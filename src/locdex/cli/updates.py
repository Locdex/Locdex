"""Privacy-limited, non-blocking Locdex release checks.

Only public package metadata is requested. Neither repository context nor
task data leaves the device; packages are never installed automatically.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests
from packaging.version import InvalidVersion, Version
from platformdirs import user_cache_dir, user_config_dir

from .. import __version__

PYPI_URL = "https://pypi.org/pypi/locdex/json"
RELEASES_URL = "https://github.com/Locdex/Locdex/releases"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 2.0


def _cache_path() -> Path:
    return Path(user_cache_dir("locdex", "Locdex")) / "updates.json"


def _settings_path() -> Path:
    return Path(user_config_dir("locdex", "Locdex")) / "updates.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temporary path avoids corruption when multiple terminals launch.
    temp = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _env_disables_checks() -> bool:
    return any(
        os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
        for name in ("LOCDEX_OFFLINE", "LOCDEX_NO_UPDATE_CHECK", "CI")
    )


def automatic_checks_enabled(*, network_allowed: bool = True) -> bool:
    return (
        network_allowed
        and not _env_disables_checks()
        and _read_json(_settings_path()).get("enabled", True) is not False
    )


def set_automatic_checks(enabled: bool) -> None:
    _write_json(_settings_path(), {"enabled": bool(enabled)})


def _valid_version(raw: Any) -> Version | None:
    if not isinstance(raw, str):
        return None
    try:
        value = Version(raw)
    except InvalidVersion:
        return None
    return value if not value.is_prerelease and not value.is_devrelease else None


def latest_stable_version() -> str:
    """Query PyPI for the newest non-yanked stable Locdex Python release."""
    response = requests.get(
        PYPI_URL,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": f"Locdex/{__version__} (public release metadata only)"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("PyPI metadata is not an object.")
    releases = payload.get("releases")
    candidates = []
    if isinstance(releases, dict):
        for key, artifacts in releases.items():
            version = _valid_version(key)
            if version is None or not isinstance(artifacts, list):
                continue
            if any(
                isinstance(artifact, dict) and not artifact.get("yanked", False)
                for artifact in artifacts
            ):
                candidates.append(version)
    else:
        info = payload.get("info") or {}
        if isinstance(info, dict):
            candidate = _valid_version(info.get("version"))
            if candidate is not None:
                candidates.append(candidate)
    if not candidates:
        raise ValueError("PyPI has no eligible stable Locdex releases.")
    return str(max(candidates))


def cached_status() -> dict[str, Any]:
    record = _read_json(_cache_path())
    latest = record.get("latest")
    checked_at = record.get("checked_at")
    try:
        current = Version(__version__)
        parsed_latest = _valid_version(latest)
        newer = parsed_latest is not None and parsed_latest > current
    except InvalidVersion:
        newer = False
    return {
        "current": __version__,
        "latest": latest if isinstance(latest, str) else None,
        "checked_at": checked_at if isinstance(checked_at, (int, float)) else None,
        "update_available": newer,
        "automatic": automatic_checks_enabled(),
    }


def check_now(*, network_allowed: bool = True) -> dict[str, Any]:
    """Explicit bounded check; honors offline restrictions but not the auto toggle."""
    if not network_allowed or _env_disables_checks():
        return {**cached_status(), "error": "Update checks disabled by offline environment."}
    try:
        latest = latest_stable_version()
        _write_json(_cache_path(), {"latest": latest, "checked_at": time.time()})
        return cached_status()
    except (requests.RequestException, ValueError, OSError) as exc:
        # The failure is operational only; never block a coding task.
        return {**cached_status(), "error": f"Update check unavailable ({type(exc).__name__})."}


def update_notice(status: dict[str, Any]) -> str | None:
    if not status.get("update_available"):
        return None
    latest = status.get("latest")
    return f"Locdex {latest} is available (installed: {__version__}). See {RELEASES_URL}"


class BackgroundUpdateCheck:
    """Run a daily throttled check without blocking the interactive prompt."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._reported_version: str | None = None
        self._network_allowed = True

    def start(self, *, network_allowed: bool = True) -> None:
        self._network_allowed = network_allowed
        if not automatic_checks_enabled(network_allowed=network_allowed):
            return
        checked_at = cached_status().get("checked_at")
        if isinstance(checked_at, (int, float)):
            elapsed = time.time() - checked_at
            if 0 <= elapsed < CHECK_INTERVAL_SECONDS:
                return
        self._thread = threading.Thread(
            target=lambda: check_now(network_allowed=network_allowed),
            daemon=True,
            name="locdex-update-check",
        )
        self._thread.start()

    def poll_notice(self) -> str | None:
        if not automatic_checks_enabled(network_allowed=self._network_allowed):
            return None
        status = cached_status()
        latest = status.get("latest")
        if not status["update_available"] or latest == self._reported_version:
            return None
        self._reported_version = latest
        return update_notice(status)
