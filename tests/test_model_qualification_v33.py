from __future__ import annotations

from locdex.qualification import model as qualification
from locdex.runtime.hardware import HardwareProfile
from locdex.runtime.manager import RuntimeStatus


def _hardware(ram: float) -> HardwareProfile:
    return HardwareProfile(
        system="TestOS",
        machine="x86_64",
        cpu_count=8,
        total_ram_gb=ram,
        available_ram_gb=ram - 1,
        backend="cpu",
        physical_cpu_count=4,
    )


def _runtime(healthy: bool = True) -> RuntimeStatus:
    return RuntimeStatus(
        installed=True,
        import_ok=True,
        healthy=healthy,
        package_version="0.3.35",
        python_version="3.11.9",
        hardware_backend="cpu",
        expected_backend="cpu",
        active_backend="cpu",
        gpu_offload_supported=False,
        wheel_index=None,
        reason="runtime ready" if healthy else "runtime broken",
    )


def test_qualification_skips_undersized_hardware(monkeypatch):
    monkeypatch.setattr(
        qualification,
        "model_status",
        lambda key: {"installed": True, "model": key},
    )
    monkeypatch.setattr(qualification, "detect_hardware", lambda: _hardware(8.0))
    monkeypatch.setattr(
        qualification,
        "runtime_status",
        lambda hardware: _runtime(True),
    )

    result = qualification.qualify_model(
        "qwen25-14b",
        save_report=False,
    )

    assert result["status"] == "skipped_hardware"
    assert result["hardware_eligible"] is False
    assert result["passed"] is False
    assert result["prompt_probe"] is None


def test_prompt_only_qualification_passes(monkeypatch):
    monkeypatch.setattr(
        qualification,
        "model_status",
        lambda key: {"installed": True, "model": key},
    )
    monkeypatch.setattr(qualification, "detect_hardware", lambda: _hardware(16.0))
    monkeypatch.setattr(
        qualification,
        "runtime_status",
        lambda hardware: _runtime(True),
    )
    monkeypatch.setattr(
        qualification,
        "run_prompt",
        lambda *args, **kwargs: {
            "model": "qwen25-7b",
            "backend": "cpu",
            "text": "LOCDEX_QUALIFY_OK",
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        },
    )

    result = qualification.qualify_model(
        "qwen25-7b",
        agent_task=False,
        save_report=False,
    )

    assert result["status"] == "passed_prompt_only"
    assert result["passed"] is True
    assert result["prompt_probe"]["passed"] is True


def test_full_qualification_requires_verified_agent_completion(monkeypatch):
    monkeypatch.setattr(
        qualification,
        "model_status",
        lambda key: {"installed": True, "model": key},
    )
    monkeypatch.setattr(qualification, "detect_hardware", lambda: _hardware(16.0))
    monkeypatch.setattr(
        qualification,
        "runtime_status",
        lambda hardware: _runtime(True),
    )
    monkeypatch.setattr(
        qualification,
        "run_prompt",
        lambda *args, **kwargs: {
            "model": "qwen25-7b",
            "backend": "cpu",
            "text": "LOCDEX_QUALIFY_OK",
            "usage": None,
        },
    )

    class FakeEngine:
        def __init__(self, model_key=None):
            self.model_key = model_key

        def execute(self, *args, **kwargs):
            return {
                "status": "completed",
                "model": self.model_key,
                "steps": 3,
                "files_modified": ["calculator.py"],
                "attempted_files_modified": ["calculator.py"],
                "verification": {
                    "passed": True,
                    "checks": [
                        {"name": "compile", "status": "passed"},
                        {"name": "tests", "status": "passed"},
                    ],
                },
                "rollback_performed": False,
            }

    monkeypatch.setattr(qualification, "AgentEngine", FakeEngine)

    result = qualification.qualify_model(
        "qwen25-7b",
        save_report=False,
    )

    assert result["status"] == "passed"
    assert result["passed"] is True
    assert result["agent_probe"]["passed"] is True
    assert result["agent_probe"]["tests_unchanged"] is True


def test_model_must_be_installed_before_qualification(monkeypatch):
    monkeypatch.setattr(
        qualification,
        "model_status",
        lambda key: {"installed": False, "model": key},
    )
    monkeypatch.setattr(qualification, "detect_hardware", lambda: _hardware(16.0))
    monkeypatch.setattr(
        qualification,
        "runtime_status",
        lambda hardware: _runtime(True),
    )

    result = qualification.qualify_model(
        "qwen25-7b",
        save_report=False,
    )

    assert result["status"] == "model_not_installed"
    assert result["passed"] is False
    assert "model install qwen25-7b" in result["error"]
