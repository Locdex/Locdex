from dataclasses import dataclass
@dataclass(frozen=True)
class RoutingPolicy:
    mode:str="balanced"; allow_cloud:bool=False; allowed_providers:tuple[str,...]=(); minimum_success_probability:float=.80; max_task_cost:float|None=None; max_latency_ms:float|None=None; cloud_context_policy:str="minimal"
    def provider_allowed(self,provider): return self.allow_cloud and (not self.allowed_providers or provider in self.allowed_providers)
