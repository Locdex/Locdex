from dataclasses import asdict,dataclass
@dataclass(frozen=True)
class RoutingRecord:
    features:dict; model:str; backend:str; success:bool; input_tokens:int; output_tokens:int; latency_ms:float|None; cost:float; attempts:int; verification:dict; router_version:str
    def to_dict(self):return asdict(self)
