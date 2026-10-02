from ..models.profiles import MODEL_PROFILES
from .model_profile import RoutingModelProfile,from_local_profile

def local_candidates(hardware):
    available=hardware.available_ram_gb or hardware.total_ram_gb; result=[from_local_profile(p) for p in MODEL_PROFILES.values() if available is None or available>=p.minimum_ram_gb]
    return result or [from_local_profile(MODEL_PROFILES["kimi"])]

def cloud_candidate(*,provider,model_id,input_cost,output_cost,context_limit=128000,preferred_context=16000,latency_ms=15000,reasoning_strength=.9,tool_call_quality=.9,vision=False):
    return RoutingModelProfile(model_id,provider,False,context_limit,preferred_context,input_cost,output_cost,average_latency_ms=latency_ms,vision=vision,tool_call_quality=tool_call_quality,reasoning_strength=reasoning_strength,privacy_class="cloud")
