from dataclasses import asdict,dataclass
@dataclass(frozen=True)
class LocalMetric:
    model:str; context_tokens:int; success:bool; latency_ms:float|None=None
    def to_dict(self):return asdict(self)
