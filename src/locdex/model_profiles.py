from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    key: str
    display_name: str
    repo_id: str
    filename_pattern: str
    expected_sha256: str | None
    approximate_size_gb: float
    minimum_ram_gb: int
    recommended_ram_gb: int
    status: str
    description: str


MODEL_PROFILES: dict[str, ModelProfile] = {
    "qwen": ModelProfile(
        key="qwen",
        display_name="Qwen3-Coder 30B-A3B Instruct (Q4_K_M)",
        repo_id="unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF",
        filename_pattern="Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf",
        expected_sha256="fadc3e5f8d42bf7e894a785b05082e47daee4df26680389817e2093056f088ad",
        approximate_size_gb=18.6,
        minimum_ram_gb=24,
        recommended_ram_gb=32,
        status="supported",
        description="Default Locdex coding model. Stronger and more established for repository-scale coding.",
    ),
    "kimi": ModelProfile(
        key="kimi",
        display_name="Qwen3.5 9B Kimi-K3 Distilled (Q4_K_M)",
        repo_id="mradermacher/Qwen3.5-9B-Kimi-k3-Distilled-GGUF",
        filename_pattern="*Q4_K_M.gguf",
        expected_sha256=None,
        approximate_size_gb=5.8,
        minimum_ram_gb=12,
        recommended_ram_gb=16,
        status="experimental",
        description="Smaller optional agentic model. Faster to download and easier to run on 16 GB machines.",
    ),
}

DEFAULT_MODEL_KEY = "qwen"


def get_model_profile(key: str) -> ModelProfile:
    normalized = key.strip().lower()
    try:
        return MODEL_PROFILES[normalized]
    except KeyError as exc:
        choices = ", ".join(sorted(MODEL_PROFILES))
        raise ValueError(f"Unknown Locdex model {key!r}. Choose one of: {choices}") from exc
