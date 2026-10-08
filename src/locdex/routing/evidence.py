from __future__ import annotations

from dataclasses import dataclass

from ..context.budget import ContextBudget, estimate_tokens
from ..context.compiler import ContextCompiler
from ..security.secrets import redact_secrets


@dataclass(frozen=True)
class EvidenceSummary:
    text: str
    tokens: int
    sections: tuple[str, ...]
    redactions: int


def collect_cloud_evidence(
    repo_path: str,
    task: str,
    *,
    context_limit: int = 128000,
    local_failure: str = "",
    prior_session: str = "",
) -> EvidenceSummary:
    """Collect then bound/redact targeted evidence before invoking any cloud API.

    This is deterministic local retrieval, not an API-generated summary.
    Source, retrieval-plan, dependency/graph information and a bounded failure
    record are assembled on-device. The cloud adapter receives one compact
    initial packet instead of a full repository dump.
    """
    limit = max(1200, min(5200, int(context_limit) // 12))
    pack = ContextCompiler().compile(
        repo_path,
        task,
        budget=ContextBudget(max_input_tokens=limit),
        cloud=True,
    )
    sections = []
    lines = ["LOCDEX CLOUD EVIDENCE PACK (collected locally; exact source may change)"]
    for item in pack.items:
        if not item.content.strip():
            continue
        if item.label == "task":
            # The agent already receives the user's task separately.
            continue
        sections.append(item.label)
        lines.extend([f"## {item.label}", item.content.strip()])
    tail_budget = max(0, min(800, 6500 - sum(len(s) for s in lines)) )
    if tail_budget and local_failure.strip():
        failure, _ = redact_secrets(local_failure[:tail_budget])
        lines.extend(["## local_outcome", failure])
        sections.append("local_outcome")
    if prior_session.strip() and sum(len(s) for s in lines) < 17000:
        previous, _ = redact_secrets(prior_session[:1200])
        lines.extend(["## prior_session", previous])
        sections.append("prior_session")
    text, further_redactions = redact_secrets("\n\n".join(lines))
    text = text[:min(18000, limit * 4)]
    return EvidenceSummary(
        text=text,
        tokens=estimate_tokens(text),
        sections=tuple(sections),
        redactions=pack.redactions + further_redactions,
    )
