from __future__ import annotations

import json

import requests

from .queue import pop, prepend
from .sanitizer import sanitize_batch
from .schema import SCHEMA_VERSION
from .settings import _validate_endpoint, enabled, endpoint


def flush(*, batch_size: int = 25, timeout: float = 2.0) -> dict:
    if not enabled():
        return {"sent": False, "reason": "disabled"}
    raw_url = endpoint()
    if not raw_url:
        return {"sent": False, "reason": "no_endpoint"}
    try:
        url = _validate_endpoint(raw_url)
    except ValueError:
        return {"sent": False, "reason": "invalid_endpoint"}
    events = pop(max(1, min(batch_size, 25)))
    if not events:
        return {"sent": False, "reason": "empty"}
    try:
        clean = sanitize_batch(events)
        payload = {"schema_version": SCHEMA_VERSION, "events": clean}
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        if len(raw) > 64_000:
            raise ValueError("Telemetry payload exceeds 64 KB.")
        response = requests.post(
            url,
            json=payload,
            timeout=timeout,
            headers={"User-Agent": "locdex-telemetry/1"},
        )
        response.raise_for_status()
    except Exception:
        # Never include remote error bodies or URLs in telemetry results.
        if enabled():
            prepend(events)
        return {"sent": False, "reason": "request_failed"}
    return {"sent": True, "events": len(clean), "status": response.status_code}
