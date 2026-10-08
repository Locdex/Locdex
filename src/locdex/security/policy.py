from dataclasses import dataclass
from enum import Enum
class RiskClass(str,Enum):
    READ="read";WRITE="write";EXECUTE="execute";NETWORK="network";GIT_WRITE="git_write";DANGEROUS="dangerous"
@dataclass(frozen=True)
class SecurityDecision: allowed:bool; reason:str
def native_authorize(risk,explicit_user_intent=False):
    if risk is RiskClass.DANGEROUS:return SecurityDecision(False,"Dangerous operations are blocked by native Locdex policy.")
    if risk is RiskClass.GIT_WRITE and not explicit_user_intent:return SecurityDecision(False,"Git mutation requires explicit user intent.")
    return SecurityDecision(True,"Allowed by native Locdex policy.")
