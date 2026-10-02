from dataclasses import asdict,dataclass
SCHEMA_VERSION=1
@dataclass(frozen=True)
class RoutingTelemetryEvent:
    event:str; router_version:str; task_class:str; language:str; repo_size_bucket:str; requested_change:str; estimated_files:int; dependency_fanout:int; has_tests:bool; has_stacktrace:bool; context_tokens:int; complexity_bucket:str; tool_intensity_bucket:str; model_id:str; backend:str; quant:str|None; os:str; ram_bucket:str; accelerator_class:str; input_tokens:int|None; output_tokens:int|None; latency_ms:float|None; tool_calls:int; edit_attempts:int; compile_passed:bool|None; tests_passed:bool|None; lint_passed:bool|None; validator_passed:bool|None; escalated:bool; user_reverted:bool; selected_model:str; selection_reason_code:str; predicted_success_selected:float|None; prediction_gap_bucket:str|None; fallback_model:str|None; route:str; router_mode:str; cost_usd:float|None
    def to_dict(self):return asdict(self)
