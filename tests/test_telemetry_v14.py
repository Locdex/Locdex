from __future__ import annotations

import json

import pytest

from locdex import telemetry


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("LOCDEX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("LOCDEX_TELEMETRY", raising=False)
    monkeypatch.delenv("LOCDEX_TELEMETRY_ENDPOINT", raising=False)


def test_off_by_default():
    assert telemetry.is_telemetry_enabled() is False
    telemetry.log_routing_outcome("bug_fix", "python", "local", True, 1)
    assert telemetry.telemetry_status()["queued_runs"] == 0


def test_enabled_telemetry_is_aggregate_only():
    telemetry.set_telemetry_enabled(True)
    telemetry.log_routing_outcome(
        "bug_fix",
        "python",
        "local",
        True,
        2,
        local_model="qwen",
        escalation_reason="none",
    )
    telemetry.log_routing_outcome(
        "bug_fix",
        "python",
        "local",
        False,
        1,
        local_model="qwen",
        escalation_reason="none",
    )
    payload = telemetry.telemetry_preview()
    assert payload["schema_version"] == 1
    assert len(payload["aggregates"]) == 1
    bucket = payload["aggregates"][0]
    assert bucket["runs"] == 2
    assert bucket["successes"] == 1
    assert bucket["total_attempts"] == 3
    serialized = json.dumps(payload).lower()
    for forbidden in ("task_text", "filepath", "repo_name", "machine_id", "prompt", "source_code"):
        assert forbidden not in serialized


def test_task_classifier_returns_fixed_label_only():
    raw = "Fix OAuth failure in AcmeSecretRepository at src/private/auth.py"
    category = telemetry.classify_task_locally(raw)
    assert category == "bug_fix"
    assert category in telemetry.TASK_CATEGORIES
    assert "acme" not in category.lower()


def test_no_endpoint_means_nothing_is_sent(monkeypatch):
    telemetry.set_telemetry_enabled(True)
    telemetry.log_routing_outcome("feature", "python", "local", True, 1)

    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be used without an endpoint")

    monkeypatch.setattr(telemetry.requests, "post", fake_post)
    result = telemetry.flush_telemetry()
    assert result["sent"] is False
    assert result["reason"] == "no_endpoint"
    assert called is False


def test_successful_flush_clears_local_aggregate(monkeypatch):
    telemetry.set_telemetry_enabled(True)
    monkeypatch.setenv("LOCDEX_TELEMETRY_ENDPOINT", "https://telemetry.example.invalid/v1/aggregate")
    telemetry.log_routing_outcome("tests", "typescript_javascript", "cloud", True, 2, cloud_provider="custom")

    class Response:
        def raise_for_status(self):
            return None

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["payload"] = json
        return Response()

    monkeypatch.setattr(telemetry.requests, "post", fake_post)
    result = telemetry.flush_telemetry()
    assert result["sent"] is True
    assert captured["payload"]["aggregates"]
    assert telemetry.telemetry_status()["queued_runs"] == 0


def test_legacy_free_text_values_collapse_to_safe_buckets():
    telemetry.set_telemetry_enabled(True)
    telemetry.log_routing_outcome("CUSTOM SECRET TASK", "super-rare-language", "mystery-route", True, 1)
    dims = telemetry.telemetry_preview()["aggregates"][0]["dimensions"]
    assert dims["task_category"] == "other"
    assert dims["language"] == "unknown"
    assert dims["route"] == "none"
