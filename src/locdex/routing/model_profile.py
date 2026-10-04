from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingModelProfile:
    model_id: str
    backend: str
    local: bool
    context_limit: int
    preferred_context: int
    input_cost_per_million: float
    output_cost_per_million: float
    average_latency_ms: float | None = None
    ram_required_gb: int | None = None
    vision: bool = False
    fim: bool = False
    tool_call_quality: float = .8
    reasoning_strength: float = .7
    privacy_class: str = "local"


def from_local_profile(profile):
    return RoutingModelProfile(
        profile.key,
        "local",
        True,
        profile.maximum_context,
        profile.preferred_context,
        0.0,
        0.0,
        ram_required_gb=profile.minimum_ram_gb,
        fim=profile.fim,
        tool_call_quality=profile.tool_call_quality,
        reasoning_strength=profile.reasoning_strength,
        privacy_class="local",
    )
