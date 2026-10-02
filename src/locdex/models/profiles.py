from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    key: str
    display_name: str
    repo_id: str
    filename_pattern: str
    approximate_size_gb: float
    minimum_ram_gb: int
    recommended_ram_gb: int
    preferred_context: int
    maximum_context: int
    status: str


MODEL_PROFILES = {
    "qwen": ModelProfile(
        key="qwen",
        display_name="Qwen3.5 35B-A3B Q4_K_S",
        repo_id="unsloth/Qwen3.5-35B-A3B-GGUF",
        filename_pattern="Qwen3.5-35B-A3B-Q4_K_S.gguf",
        approximate_size_gb=20.7,
        minimum_ram_gb=28,
        recommended_ram_gb=32,
        preferred_context=16384,
        maximum_context=262144,
        status="supported",
    ),
    "kimi": ModelProfile(
        key="kimi",
        display_name="Qwen3.5 9B Kimi-K3 Distilled Q4_K_M",
        repo_id="mradermacher/Qwen3.5-9B-Kimi-k3-Distilled-GGUF",
        filename_pattern="Qwen3.5-9B-Kimi-k3-Distilled.Q4_K_M.gguf",
        approximate_size_gb=5.78,
        minimum_ram_gb=12,
        recommended_ram_gb=16,
        preferred_context=8192,
        maximum_context=262144,
        status="experimental",
    ),
}

DEFAULT_MODEL_KEY = "qwen"


def get_model_profile(key: str) -> ModelProfile:
    try:
        return MODEL_PROFILES[key.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown model profile: {key}") from exc
