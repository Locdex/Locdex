"""Explicit llama.cpp context overrides must remain bounded and opt-in."""
from types import SimpleNamespace

import pytest

from locdex.runtime import llama_cpp


@pytest.fixture
def fake_backend(monkeypatch):
    monkeypatch.setattr(llama_cpp, "installed_model_path", lambda key: "/models/model.gguf")
    monkeypatch.setattr(llama_cpp, "runtime_status", lambda hw: SimpleNamespace(
        installed=True, import_ok=True, healthy=True, active_backend="cpu",
    ))
    return SimpleNamespace(
        system="Linux", machine="x86_64", cpu_count=2,
        total_ram_gb=3.7, available_ram_gb=0.8, backend="cpu",
        physical_cpu_count=2,
    )


def test_default_model_context_unchanged(monkeypatch, fake_backend):
    monkeypatch.delenv("LOCDEX_LLAMA_CONTEXT_TOKENS", raising=False)
    plan = llama_cpp.plan_inference(model_key="qwen25-3b", hardware=fake_backend)
    assert plan.n_ctx == 6144


def test_explicit_reduced_context(monkeypatch, fake_backend):
    monkeypatch.setenv("LOCDEX_LLAMA_CONTEXT_TOKENS", "4096")
    plan = llama_cpp.plan_inference(model_key="qwen25-3b", hardware=fake_backend)
    assert plan.n_ctx == 4096


@pytest.mark.parametrize("invalid", ["abc", "1024", "8192", "4097"])
def test_invalid_context_rejected(monkeypatch, fake_backend, invalid):
    monkeypatch.setenv("LOCDEX_LLAMA_CONTEXT_TOKENS", invalid)
    with pytest.raises(llama_cpp.RuntimeExecutionError, match="LOCDEX_LLAMA_CONTEXT_TOKENS"):
        llama_cpp.plan_inference(model_key="qwen25-3b", hardware=fake_backend)
