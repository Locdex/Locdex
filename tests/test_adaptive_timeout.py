from __future__ import annotations

import json

import pytest

from locdex.runtime.hardware import HardwareProfile
from locdex.runtime.timeout_policy import (
    estimate_inference_timeout,
    observed_speed,
    record_generation_speed,
    record_inference_timeout,
)


def cpu(ram=12, cores=4):
    return HardwareProfile(
        "Windows", "AMD64", cores * 2, 16, ram, "cpu",
        physical_cpu_count=cores,
    )


def gpu():
    return HardwareProfile(
        "Windows", "AMD64", 16, 32, 24, "cuda",
        physical_cpu_count=8, accelerator="nvidia",
        vram_free_gb=24,
    )


def test_auto_timeout_adapts_to_model_hardware_and_context(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    small = estimate_inference_timeout("smoke", hardware=cpu())
    large = estimate_inference_timeout("qwen25-14b", hardware=cpu(), max_tokens=512)
    gpu_budget = estimate_inference_timeout("qwen25-14b", hardware=gpu(), max_tokens=512)
    long_context = estimate_inference_timeout("smoke", hardware=cpu(), prompt_tokens=6000)
    assert 35 <= small.load_seconds <= 210
    assert 35 <= small.generate_seconds <= 360
    assert large.generate_seconds > small.generate_seconds
    assert gpu_budget.generate_seconds < large.generate_seconds
    assert long_context.generate_seconds > small.generate_seconds
    assert small.source == "model_and_hardware_estimate"


def test_cloud_enabled_prefers_shorter_timeout(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    normal = estimate_inference_timeout("qwen", hardware=cpu())
    cloud = estimate_inference_timeout("qwen", hardware=cpu(), prefer_cloud_fallback=True)
    assert cloud.load_seconds <= normal.load_seconds
    assert cloud.generate_seconds <= normal.generate_seconds
    assert cloud.generate_seconds <= 110


def test_explicit_override_remains_authoritative(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", "135")
    for key in ("smoke", "qwen"):
        budget = estimate_inference_timeout(key, hardware=cpu(), prefer_cloud_fallback=True)
        assert budget.load_seconds == 135
        assert budget.generate_seconds == 135
        assert budget.source == "explicit_override"


def test_local_calibration_is_used_without_tracking_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    baseline = estimate_inference_timeout("smoke", hardware=cpu())
    assert record_generation_speed("smoke", "cpu", seconds=64, output_tokens=64)
    assert observed_speed("smoke", "cpu") == 1
    calibrated = estimate_inference_timeout("smoke", hardware=cpu())
    assert calibrated.source == "measured_speed"
    assert calibrated.generate_seconds > baseline.generate_seconds
    sample_file = tmp_path / "inference" / "speed-v1.json"
    payload = json.loads(sample_file.read_text(encoding="utf-8"))
    assert list(payload) == ["smoke:cpu"]
    assert "hardware_id" not in sample_file.read_text(encoding="utf-8")
    assert not record_generation_speed("smoke", "cpu", seconds=0, output_tokens=10)


def test_invalid_override_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", "not-a-number")
    budget = estimate_inference_timeout("smoke", hardware=cpu())
    assert budget.source == "model_and_hardware_estimate"


def test_constrained_dual_core_cpu_has_realistic_cold_probe_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", raising=False)
    # Matches the reporting user's CPU class and available memory.
    slow_laptop = HardwareProfile(
        system="Windows",
        machine="AMD64",
        cpu_count=4,
        total_ram_gb=7.72,
        available_ram_gb=2.06,
        backend="cpu",
        physical_cpu_count=2,
    )
    budget = estimate_inference_timeout(
        "smoke", hardware=slow_laptop, max_tokens=32, prompt_tokens=10,
    )
    assert 70 <= budget.load_seconds <= 210
    assert 115 <= budget.generate_seconds <= 360
    assert budget.source == "model_and_hardware_estimate"
    assert budget.backend == "cpu"


def test_hard_timeout_increases_next_local_budget_without_inventing_speed(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", raising=False)
    before = estimate_inference_timeout(
        "smoke", hardware=cpu(), max_tokens=16,
    )
    assert record_inference_timeout(
        "smoke", "cpu", phase="generating", seconds=65,
    )
    after = estimate_inference_timeout(
        "smoke", hardware=cpu(), max_tokens=16,
    )
    assert after.generate_seconds >= 107
    assert after.generate_seconds > before.generate_seconds
    assert observed_speed("smoke", "cpu") is None
    assert after.source == "model_and_hardware_estimate"


def test_loading_timeout_calibrates_independently_and_survives_success(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", raising=False)
    assert record_inference_timeout(
        "smoke", "cpu", phase="loading", seconds=80,
    )
    assert record_generation_speed(
        "smoke", "cpu", seconds=64, output_tokens=64,
    )
    next_budget = estimate_inference_timeout("smoke", hardware=cpu())
    assert next_budget.load_seconds >= 132
    assert next_budget.source == "measured_speed"
    raw = json.loads((tmp_path / "inference" / "speed-v1.json").read_text())
    assert raw["smoke:cpu"]["load_timeout_floor"] >= 132
    assert "tokens_per_second" in raw["smoke:cpu"]


def test_override_remains_authoritative_after_timeout_history(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", raising=False)
    assert record_inference_timeout(
        "smoke", "cpu", phase="generating", seconds=100,
    )
    monkeypatch.setenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", "50")
    budget = estimate_inference_timeout("smoke", hardware=cpu())
    assert budget.generate_seconds == 50
    assert budget.load_seconds == 50
