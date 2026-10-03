from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import locdex.runtime.llama_cpp as runtime_module
from locdex.runtime.hardware import HardwareProfile
from locdex.runtime.llama_cpp import InferencePlan


def test_plan_inference_for_cpu_smoke(monkeypatch, tmp_path):
    model = tmp_path / "smoke.gguf"
    model.write_bytes(b"gguf")

    monkeypatch.setattr(runtime_module, "selected_model_key", lambda: "smoke")
    monkeypatch.setattr(runtime_module, "installed_model_path", lambda key: model)
    monkeypatch.setattr(
        runtime_module,
        "runtime_status",
        lambda hardware: SimpleNamespace(
            installed=True,
            import_ok=True,
            healthy=True,
            active_backend="cpu",
            reason="ready",
        ),
    )

    hardware = HardwareProfile(
        "Windows",
        "AMD64",
        4,
        7.7,
        2.0,
        "cpu",
        cpu_name="Intel Test",
        physical_cpu_count=2,
    )
    plan = runtime_module.plan_inference(hardware=hardware)
    assert plan.model_key == "smoke"
    assert plan.n_ctx == 4096
    assert plan.n_threads == 2
    assert plan.n_gpu_layers == 0


def test_run_prompt_returns_chat_text(monkeypatch):
    plan = InferencePlan(
        model_key="smoke",
        model_path="smoke.gguf",
        backend="cpu",
        n_ctx=4096,
        n_threads=2,
        n_gpu_layers=0,
        max_tokens=32,
        temperature=0.1,
    )

    class FakeLlama:
        def create_chat_completion(self, **kwargs):
            return {
                "choices": [{"message": {"content": "LOCDEX_OK"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            }

    monkeypatch.setattr(runtime_module, "plan_inference", lambda **kwargs: plan)
    monkeypatch.setattr(runtime_module, "_load_llama", lambda supplied_plan: FakeLlama())

    result = runtime_module.run_prompt("Reply exactly: LOCDEX_OK")
    assert result["text"] == "LOCDEX_OK"
    assert result["model"] == "smoke"
    assert result["backend"] == "cpu"
