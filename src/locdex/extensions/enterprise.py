from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


@dataclass(frozen=True)
class ToolAuthorizationRequest:
    tool_name: str
    risk_class: str
    args: dict[str, Any]
    workspace: str


@dataclass(frozen=True)
class CloudAuthorizationRequest:
    provider: str
    model: str
    context_policy: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost: float | None = None


@dataclass(frozen=True)
class SecretRequest:
    name: str
    purpose: str


@dataclass(frozen=True)
class SecretResponse:
    value: str
    source: str


@dataclass(frozen=True)
class InferenceRequest:
    provider: str | None
    model: str | None
    privacy_policy: str
    required_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    payload: dict[str, Any]


@runtime_checkable
class SandboxProvider(Protocol):
    def execute(self, request: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class InferenceGateway(Protocol):
    def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class EnterpriseExtension(Protocol):
    """Public OSS contract implemented by optional private enterprise packages."""

    def authorize_tool(self, request: ToolAuthorizationRequest) -> PolicyDecision: ...
    def authorize_cloud(self, request: CloudAuthorizationRequest) -> PolicyDecision: ...
    def resolve_secret(self, request: SecretRequest) -> SecretResponse | None: ...
    def select_inference_gateway(self, request: InferenceRequest) -> InferenceGateway | None: ...
    def sandbox_provider(self) -> SandboxProvider | None: ...
    def emit_audit_event(self, event: AuditEvent) -> None: ...


class NullEnterpriseExtension:
    """Default OSS implementation. It adds no enterprise restrictions or dependencies."""

    def authorize_tool(self, request: ToolAuthorizationRequest) -> PolicyDecision:
        return PolicyDecision(Decision.ALLOW, "No enterprise policy configured.")

    def authorize_cloud(self, request: CloudAuthorizationRequest) -> PolicyDecision:
        return PolicyDecision(Decision.ALLOW, "No enterprise policy configured.")

    def resolve_secret(self, request: SecretRequest) -> SecretResponse | None:
        return None

    def select_inference_gateway(self, request: InferenceRequest) -> InferenceGateway | None:
        return None

    def sandbox_provider(self) -> SandboxProvider | None:
        return None

    def emit_audit_event(self, event: AuditEvent) -> None:
        return None
