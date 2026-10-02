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
    preferred_context: int
    maximum_context: int
    status: str
    description: str
    revision: str | None = None


MODEL_PROFILES = {
    "smoke": ModelProfile(
        key="smoke",
        display_name="Qwen2.5-Coder 1.5B Instruct Q4_K_M",
        repo_id="Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        filename_pattern="qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        expected_sha256="cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046",
        approximate_size_gb=1.12,
        minimum_ram_gb=4,
        recommended_ram_gb=8,
        preferred_context=4096,
        maximum_context=32768,
        status="development",
        description=(
            "Development-only model for runtime, inference, and agent smoke tests on low-spec hardware. "
            "Not the recommended production Locdex coding model."
        ),
    ),
    "qwen": ModelProfile(
        key="qwen",
        display_name="Qwen3.5 35B-A3B Q4_K_S",
        repo_id="unsloth/Qwen3.5-35B-A3B-GGUF",
        filename_pattern="Qwen3.5-35B-A3B-Q4_K_S.gguf",
        expected_sha256="ee93ceffed5ce4df8b09bcbaf59a286d531025a1ebde9cf204c74e800c47d57e",
        approximate_size_gb=20.7,
        minimum_ram_gb=28,
        recommended_ram_gb=32,
        preferred_context=16384,
        maximum_context=262144,
        status="supported",
        description="Primary supported Locdex local coding model for 32 GB-class systems.",
        revision="ac1c149b8500aa4cd8cbe9b4721804b2fccb82ee",
    ),
    "kimi": ModelProfile(
        key="kimi",
        display_name="Qwen3.5 9B Kimi-K3 Distilled Q4_K_M",
        repo_id="mradermacher/Qwen3.5-9B-Kimi-k3-Distilled-GGUF",
        filename_pattern="Qwen3.5-9B-Kimi-k3-Distilled.Q4_K_M.gguf",
        expected_sha256="ff0649d92045b564daf4e0b9b0e6b21c6b83b2b1b59448554cf778ad206695f7",
        approximate_size_gb=5.78,
        minimum_ram_gb=12,
        recommended_ram_gb=16,
        preferred_context=8192,
        maximum_context=262144,
        status="experimental",
        description="Optional experimental Kimi-K3-distilled coding profile for 16 GB-class systems.",
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
