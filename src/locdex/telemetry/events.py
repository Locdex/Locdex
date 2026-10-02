from .schema import RoutingTelemetryEvent
def _bucket(v):return "low" if v<.35 else "medium" if v<.7 else "high"
def _ram_bucket(gb):
    if gb is None:return "unknown"
    if gb<12:return "lt12"
    if gb<20:return "16gb_class"
    if gb<28:return "24gb_class"
    if gb<48:return "32gb_class"
    return "64gb_plus"
def _prediction_gap(d):
    vals=sorted(d.predictions.values(),reverse=True)
    if len(vals)<2:return None
    g=vals[0]-vals[1];return "tight" if g<.03 else "close" if g<.08 else "clear"
def build_routing_event(*,task,decision,hardware,quant=None,input_tokens=None,output_tokens=None,latency_ms=None,tool_calls=0,edit_attempts=0,compile_passed=None,tests_passed=None,lint_passed=None,validator_passed=None,escalated=False,user_reverted=False):
    acc="cpu" if hardware.backend=="cpu" else hardware.backend;reason="local_likely_success" if decision.route=="local" else "cloud_likely_success"
    return RoutingTelemetryEvent("routing_outcome",decision.router_version,task.task_class,task.language,task.repo_size_bucket,task.requested_change,task.estimated_files,task.dependency_fanout,task.has_tests,task.has_stacktrace,task.context_estimate,_bucket(task.reasoning_complexity),_bucket(task.tool_intensity),decision.model,decision.route,quant,hardware.system.lower(),_ram_bucket(hardware.available_ram_gb or hardware.total_ram_gb),acc,input_tokens,output_tokens,latency_ms,tool_calls,edit_attempts,compile_passed,tests_passed,lint_passed,validator_passed,escalated,user_reverted,decision.model,reason,decision.predicted_success,_prediction_gap(decision),decision.fallback,decision.route,"balanced",decision.predicted_cost)
