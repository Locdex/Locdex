from dataclasses import dataclass
from .scorer import RuleScorer
from .session import RoutingSession
@dataclass(frozen=True)
class RoutingDecision:
    model:str; route:str; confidence:float; predicted_success:float; predicted_cost:float; predicted_latency_ms:float|None; reason:str; fallback:str|None; predictions:dict[str,float]; router_version:str="rules-v0"
class LearnedRouter:
    def __init__(self,scorer=None):
        if scorer is not None:self.scorer=scorer;return
        try:
            from .updater import active_path
            from .artifact import load_artifact
            from .artifact_scorer import ArtifactScorer
            p=active_path(); self.scorer=ArtifactScorer(load_artifact(p)) if p.exists() else RuleScorer()
        except Exception:self.scorer=RuleScorer()
    def route(self,*,task,models,policy,session=None):
        session=session or RoutingSession(); eligible=[]
        for m in models:
            if not m.local and not policy.provider_allowed(m.backend):continue
            if policy.mode=="local_only" and not m.local:continue
            p=self.scorer.predict(task,m)
            if policy.max_task_cost is not None and p.predicted_cost>policy.max_task_cost:continue
            if policy.max_latency_ms is not None and p.predicted_latency_ms is not None and p.predicted_latency_ms>policy.max_latency_ms:continue
            eligible.append((m,p))
        if not eligible: raise RuntimeError("No model satisfies the current routing/privacy/budget policy.")
        def utility(x):
            m,p=x; sw=session.switching_penalty(m.model_id)
            if policy.mode=="quality":return p.predicted_success-sw
            if policy.mode=="fast":return p.predicted_success-min(.25,(p.predicted_latency_ms or (45000 if m.local else 15000))/200000)-sw
            return p.predicted_success+(.035 if m.local else 0)-min(.2,p.predicted_cost*1.5)-sw
        ranked=sorted(eligible,key=utility,reverse=True); chosen,cp=ranked[0]
        if cp.predicted_success<policy.minimum_success_probability: chosen,cp=max(eligible,key=lambda x:x[1].predicted_success-session.switching_penalty(x[0].model_id))
        fallback=next((m.model_id for m,p in ranked if m.model_id!=chosen.model_id and p.predicted_success>=policy.minimum_success_probability),None)
        preds={m.model_id:p.predicted_success for m,p in eligible}; route="local" if chosen.local else "cloud"
        reason=f"{policy.mode}: selected allowed model with predicted success {cp.predicted_success:.0%}"
        return RoutingDecision(chosen.model_id,route,cp.predicted_success,cp.predicted_success,cp.predicted_cost,cp.predicted_latency_ms,reason,fallback,preds)
