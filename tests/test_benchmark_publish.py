from __future__ import annotations

import json

import pytest

from locdex.benchmark.publish import (
    export_qualification, sanitize_qualification, summarize_directory,
    validate_public_record,
)


def fixture():
    return {
        "schema_version": 1,
        "model": "smoke",
        "status": "passed",
        "hardware_tier": "4-8 GB dev",
        "hardware": {"cpu_name": "Private CPU", "gpu_name": "Personal device"},
        "runtime": {"active_backend": "cpu", "import_error": "PRIVATE ERROR"},
        "prompt_probe": {
            "passed": True, "elapsed_seconds": 3.54,
            "text": "PRIVATE PROMPT AND RESPONSE",
        },
        "agent_probe": {
            "passed": True, "elapsed_seconds": 9.8, "steps": 3,
            "tests_unchanged": True,
            "verification": {"passed": True, "logs": "PRIVATE_SOURCE"},
            "files_modified": ["private/path/calculator.py"],
        },
        "report_path": "C:/Users/secret/private.json",
        "error": "private errors",
    }


def test_sanitize_qualification_removes_raw_identifiers():
    row = sanitize_qualification(fixture())
    serialized = json.dumps(row)
    for value in ("PRIVATE", "C:/Users", "calculator.py", "Personal device"):
        assert value not in serialized
    assert row["suite"] == "locdex-qualification-v1"
    assert row["agent_passed"] is True
    validate_public_record(row)


def test_export_and_summary_use_only_allowlisted_fields(tmp_path):
    source = tmp_path / "private.json"
    output = tmp_path / "results" / "smoke.json"
    source.write_text(json.dumps(fixture()), encoding="utf-8")
    record = export_qualification(str(source), str(output))
    assert record["status"] == "passed"
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["model"] == "smoke"
    aggregate = summarize_directory(str(output.parent))
    assert aggregate["records"] == 1
    assert aggregate["models"]["smoke"]["agent_passes"] == 1
    assert "not a general coding benchmark" in aggregate["note"]


def test_invalid_or_overly_verbose_public_record_rejected():
    row = sanitize_qualification(fixture())
    row["filename"] = "private.py"
    with pytest.raises(ValueError, match="extra fields"):
        validate_public_record(row)


def test_unqualified_status_is_not_a_pass():
    raw = fixture()
    raw["status"] = "prompt_failed"
    raw["prompt_probe"] = {"passed": False, "elapsed_seconds": 2.5}
    raw["agent_probe"] = None
    row = sanitize_qualification(raw)
    assert row["prompt_passed"] is False
    assert row["agent_passed"] is None


def test_unknown_model_and_status_cannot_be_published():
    raw = fixture()
    raw["model"] = "secret/proprietary-model"
    with pytest.raises(ValueError):
        sanitize_qualification(raw)
    raw = fixture()
    raw["status"] = "magical_score"
    with pytest.raises(ValueError):
        sanitize_qualification(raw)
