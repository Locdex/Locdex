from locdex.routing.training.evaluator import calibration_bins
from locdex.routing.training.labels import success_label
from locdex.routing.training.train import build_lookup_artifact, train_lookup_file, training_contract


def test_verification_is_primary_training_label():
    assert success_label(
        compile_passed=True,
        tests_passed=True,
        lint_passed=True,
        validator_passed=True,
        escalated=False,
        reverted=False,
    )
    assert not success_label(
        compile_passed=True,
        tests_passed=False,
        lint_passed=True,
        validator_passed=True,
        escalated=False,
        reverted=False,
    )


def test_training_contract_is_offline():
    contract = training_contract()
    assert contract["online_training"] is False
    assert contract["raw_prompts_or_code"] is False


def test_calibration_bins_compare_prediction_to_outcome():
    rows = [
        {"predicted_success": .91, "success": True},
        {"predicted_success": .92, "success": False},
    ]
    assert calibration_bins(rows)[-1]["n"] == 2


def test_lookup_training_builds_versioned_router_artifact(tmp_path):
    rows = [
        {
            "event": "routing_outcome",
            "task_class": "bug_fix",
            "model_id": "qwen",
            "compile_passed": True,
            "tests_passed": True,
            "lint_passed": True,
            "validator_passed": True,
            "escalated": False,
            "user_reverted": False,
            "latency_ms": 1000,
            "cost_usd": 0.0,
            "edit_attempts": 1,
        },
        {
            "event": "routing_outcome",
            "task_class": "bug_fix",
            "model_id": "qwen",
            "compile_passed": True,
            "tests_passed": False,
            "lint_passed": True,
            "validator_passed": False,
            "escalated": True,
            "user_reverted": True,
            "latency_ms": 2000,
            "cost_usd": 0.0,
            "edit_attempts": 2,
        },
    ]

    artifact = build_lookup_artifact(rows, version="test")
    assert artifact["version"] == "test"
    assert artifact["samples"] == 2
    assert artifact["table"]["bug_fix"]["qwen"]["success_rate"] == .5

    source = tmp_path / "events.jsonl"
    source.write_text(
        "\n".join(__import__("json").dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "router.json"
    result = train_lookup_file(source, output, version="test")
    assert result["samples"] == 2
    assert output.is_file()
