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
    hardware_tier: str = "general"
    family: str = "unknown"
    tool_call_quality: float = 0.74
    reasoning_strength: float = 0.72
    fim: bool = False


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
            "Development-only model for runtime, inference, and agent smoke tests. "
            "Not recommended for production coding-agent work."
        ),
        hardware_tier="4-8 GB dev",
        family="qwen2.5-coder",
        tool_call_quality=0.56,
        reasoning_strength=0.48,
        fim=True,
    ),
    "qwen25-3b": ModelProfile(
        key="qwen25-3b",
        display_name="Qwen2.5-Coder 3B Instruct Q4_K_M",
        repo_id="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
        filename_pattern="qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        expected_sha256=None,
        approximate_size_gb=2.10,
        minimum_ram_gb=6,
        recommended_ram_gb=8,
        preferred_context=6144,
        maximum_context=32768,
        status="experimental",
        description="Lightweight coding-agent option for 8 GB-class systems.",
        hardware_tier="8 GB",
        family="qwen2.5-coder",
        tool_call_quality=0.66,
        reasoning_strength=0.60,
        fim=True,
    ),
    "qwen25-7b": ModelProfile(
        key="qwen25-7b",
        display_name="Qwen2.5-Coder 7B Instruct Q4_K_M",
        repo_id="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
        filename_pattern="qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        expected_sha256=None,
        approximate_size_gb=4.68,
        minimum_ram_gb=8,
        recommended_ram_gb=12,
        preferred_context=8192,
        maximum_context=32768,
        status="supported",
        description="Balanced local coding model for 8-12 GB-class systems.",
        hardware_tier="8-12 GB",
        family="qwen2.5-coder",
        tool_call_quality=0.76,
        reasoning_strength=0.70,
        fim=True,
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
        description="Optional Kimi-K3-distilled coding profile for 16 GB-class systems.",
        hardware_tier="16 GB",
        family="kimi-distilled",
        tool_call_quality=0.78,
        reasoning_strength=0.76,
    ),
    "qwen25-14b": ModelProfile(
        key="qwen25-14b",
        display_name="Qwen2.5-Coder 14B Instruct Q4_K_M",
        repo_id="Qwen/Qwen2.5-Coder-14B-Instruct-GGUF",
        filename_pattern="qwen2.5-coder-14b-instruct-q4_k_m.gguf",
        expected_sha256=None,
        approximate_size_gb=8.99,
        minimum_ram_gb=14,
        recommended_ram_gb=16,
        preferred_context=12288,
        maximum_context=32768,
        status="supported",
        description="Higher-quality dense coding option for 16 GB-class systems.",
        hardware_tier="16 GB",
        family="qwen2.5-coder",
        tool_call_quality=0.83,
        reasoning_strength=0.79,
        fim=True,
    ),
    "deepseek-lite": ModelProfile(
        key="deepseek-lite",
        display_name="DeepSeek-Coder-V2-Lite Instruct Q4_K_M",
        repo_id="second-state/DeepSeek-Coder-V2-Lite-Instruct-GGUF",
        filename_pattern="DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf",
        expected_sha256=None,
        approximate_size_gb=10.4,
        minimum_ram_gb=16,
        recommended_ram_gb=20,
        preferred_context=12288,
        maximum_context=128000,
        status="experimental",
        description="Alternative coding model for 16-20 GB-class systems.",
        hardware_tier="16-20 GB",
        family="deepseek-coder-v2",
        tool_call_quality=0.79,
        reasoning_strength=0.78,
    ),
    "qwen3-coder": ModelProfile(
        key="qwen3-coder",
        display_name="Qwen3-Coder 30B-A3B Instruct Q4_K_M",
        repo_id="tensorblock/Qwen_Qwen3-Coder-30B-A3B-Instruct-GGUF",
        filename_pattern="Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf",
        expected_sha256=None,
        approximate_size_gb=18.56,
        minimum_ram_gb=24,
        recommended_ram_gb=32,
        preferred_context=16384,
        maximum_context=262144,
        status="experimental",
        description="Modern MoE coding model for 24-32 GB-class systems.",
        hardware_tier="24-32 GB",
        family="qwen3-coder",
        tool_call_quality=0.88,
        reasoning_strength=0.86,
        fim=True,
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
        hardware_tier="32 GB",
        family="qwen3.5",
        tool_call_quality=0.90,
        reasoning_strength=0.88,
        fim=True,
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
