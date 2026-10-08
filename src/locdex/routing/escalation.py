from dataclasses import dataclass
@dataclass(frozen=True)
class EscalationDecision: reconsider_route:bool; reason:str

def escalation_boundary(event,*,verification_passed=None):
    if event in {"new_task","model_runtime_failure"}: return EscalationDecision(True,event)
    if event=="verification" and verification_passed is False:return EscalationDecision(True,"verification_failed")
    return EscalationDecision(False,"keep_session_model")
