"""LocdexBench manifest, fixture-pin, and protected-file regression tests."""
from __future__ import annotations

import copy
from dataclasses import asdict
from pathlib import Path

import pytest

from locdex.benchmark.controls import validate_agent_changes, validate_controls
from locdex.benchmark.manifest import (
    ManifestError, load_manifest, load_suite, parse_manifest, verify_pinned_fixture,
)


ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "benchmarks/tasks/py-arithmetic-edge-001.yaml"


def raw():
    task = load_manifest(TASK)
    item = asdict(task)
    item["visible_checks"] = [list(cmd) for cmd in task.visible_checks]
    item["allowed_writes"] = list(task.allowed_writes)
    return item


def test_manifest_load_and_pinned_fixture():
    task = load_manifest(TASK)
    assert task.suite == "locdexbench-v0"
    assert task.base_commit == "2d7303ce8aa54f907efc9eed42987a5ae7cb7523"
    verify_pinned_fixture(task, ROOT)


def test_load_suite_rejects_duplicates(tmp_path):
    text = TASK.read_text(encoding="utf-8")
    (tmp_path / "one.yaml").write_text(text, encoding="utf-8")
    (tmp_path / "two.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ManifestError, match="Duplicate"):
        load_suite(tmp_path)


@pytest.mark.parametrize("field,value", [
    ("suite", "old-bench"),
    ("id", "../escape"),
    ("category", "download-and-run"),
    ("fixture", "../../etc"),
    ("fixture", "benchmarks/fixtures/other\\test"),
    ("base_commit", "main"),
    ("hidden_grader", "benchmarks/fixtures/py-arithmetic-edge-001/test_hidden.py"),
    ("reference_file", "/tmp/correct.py"),
    ("allowed_writes", ["core.py", "tests/test_visible.py"]),
    ("visible_checks", [["sh", "-c", "curl https://example.com"]]),
])
def test_invalid_or_unsafe_fields_rejected(field, value):
    item = raw()
    item[field] = value
    with pytest.raises(ManifestError):
        parse_manifest(item)


def test_unknown_field_and_boolean_limits_rejected():
    item = raw()
    item["secret"] = "should not be accepted"
    with pytest.raises(ManifestError, match="extra"):
        parse_manifest(item)
    item = raw()
    item["limits"]["model_steps"] = True
    with pytest.raises(ManifestError, match="model_steps"):
        parse_manifest(item)
    item = raw()
    item["limits"]["network"] = True
    with pytest.raises(ManifestError, match="disable network"):
        parse_manifest(item)


def test_tampered_pinned_fixture_fails(tmp_path):
    task = load_manifest(TASK)
    with pytest.raises(ManifestError, match="commit"):
        verify_pinned_fixture(
            parse_manifest({**raw(), "base_commit": "0" * 40}), ROOT,
        )


def test_fixture_control_ground_truth():
    task = load_manifest(TASK)
    outcome = validate_controls(task, ROOT)
    assert outcome.passed
    assert outcome.baseline_visible_failed
    assert outcome.reference_hidden_passed
    assert outcome.negative_control_rejected


def test_protected_tests_and_undeclared_writes_rejected(tmp_path):
    task = load_manifest(TASK)
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "core.py").write_text("before", encoding="utf-8")
    (after / "core.py").write_text("after", encoding="utf-8")
    validate_agent_changes(task, before, after)
    (after / "tests").mkdir()
    (after / "tests/test_visible.py").write_text("bypass", encoding="utf-8")
    with pytest.raises(ManifestError, match="protected"):
        validate_agent_changes(task, before, after)
