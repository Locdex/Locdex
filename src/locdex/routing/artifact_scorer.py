from .artifact import RouterArtifact
from .scorer import ModelPrediction,RuleScorer
class ArtifactScorer:
    def __init__(self,artifact:RouterArtifact,fallback=None): self.artifact=artifact; self.fallback=fallback or RuleScorer()
    def predict(self,task,model):
        base=self.fallback.predict(task,model); row=self.artifact.table.get(task.task_class,{}).get(model.model_id) or self.artifact.global_models.get(model.model_id)
        if not row:return base
        s=max(.01,min(.99,float(row.get("success_rate",base.predicted_success)))); c=0.0 if model.local else float(row.get("avg_cost",base.predicted_cost)); l=row.get("avg_latency_ms",base.predicted_latency_ms); a=float(row.get("avg_attempts",base.expected_attempts))
        return ModelPrediction(model.model_id,round(s,4),round(c,6),None if l is None else float(l),round(a,3))
