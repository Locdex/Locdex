from dataclasses import dataclass
@dataclass(frozen=True)
class ModelPrediction:
    model_id:str; predicted_success:float; predicted_cost:float; predicted_latency_ms:float|None; expected_attempts:float
class RuleScorer:
    def predict(self,task,model):
        base=.88 if model.model_id=="qwen" else .72 if model.model_id=="kimi" else .92
        if task.task_class in {"architecture","debugging"}:base+=(model.reasoning_strength-.7)*.22
        if task.task_class in {"testing","repo_navigation","small_edit"} and model.local:base+=.04
        if task.tool_intensity>.7:base+=(model.tool_call_quality-.7)*.12
        if task.requires_long_context and model.preferred_context<16000:base-=.08
        if task.current_attempt>1:base-=min(.12,.04*(task.current_attempt-1))
        if task.previous_model_failed==model.model_id:base-=.18
        success=max(.05,min(.99,base)); inp=max(1000,task.context_estimate or 5000); out=1800 if task.reasoning_complexity>.65 else 1000
        cost=(inp/1e6)*model.input_cost_per_million+(out/1e6)*model.output_cost_per_million
        return ModelPrediction(model.model_id,round(success,4),round(cost,6),model.average_latency_ms,round(1+max(0,.9-success)*2.5,3))
