# Locdex v3.3 Build Specification

This document is normative for the public Locdex repository.

## Core boundaries

1. The agent MUST NOT depend directly on a specific local or cloud model implementation.
2. Task state MUST live outside the model transcript.
3. Repository Intelligence and Context Compilation MUST remain separate subsystems.
4. Cloud models MUST NOT receive direct filesystem access.
5. Verification MUST be deterministic and external to model self-report.
6. Hardware may recommend a model but MUST NOT silently replace an explicit user selection.
7. Git mutations MUST require explicit current-request intent.
8. Enterprise implementations MUST remain outside the public repository.

## Model profiles

`qwen` MUST identify the supported Qwen3.5 35B-A3B Q4_K_S profile.

`kimi` MUST identify the experimental Qwen3.5 9B Kimi-K3 Distilled Q4_K_M profile unless a future documented migration deliberately changes it.

## Context

Context MUST be budgeted from the selected model’s preferred working context rather than automatically filling its maximum context window.

Cloud context defaults to Minimal policy and MUST pass through secret filtering and privacy policy before transport.

Context packs SHOULD support:

- metadata/signatures;
- compressed support context;
- exact source for code/tests actually needed;
- stale-context removal;
- fingerprints/cache reuse;
- progressive disclosure.

## Routing

The routing API MUST accept task profile, available model profiles, user policy/budget, and session state.

Hard constraints MUST filter impossible/forbidden candidates before learned scoring.

The router SHOULD predict `P(success | task, model)` separately per model rather than train a fixed classifier whose labels are model names.

Router decisions MUST be locally inspectable and include stable reason codes, selected model, predicted success, expected cost/latency, fallback, and router version.

Launch routing is `rules-v0`. Learned artifacts MUST be versioned and checksum-verified. Artifact failure MUST fall back to `rules-v0`.

Routing SHOULD remain session-aware; switching should occur at meaningful boundaries, not every message/tool call.

## Telemetry

Shared telemetry MUST be OFF by default.

BASIC telemetry MUST use an exact allow-list schema and MUST reject unknown fields.

BASIC telemetry MUST NOT include source code, prompts, model output text, diffs, filenames, paths, repository/branch identity, credentials, environment values, company/user identity, or persistent installation/device IDs.

No configured endpoint MUST mean no telemetry network call.

Events MUST queue locally and upload in bounded batches. Upload failure MUST preserve/requeue unsent events.

RESEARCH consent MUST be separate from BASIC. It MUST NOT silently authorize shadow evaluation of private user code.

Router prediction metadata SHOULD be collected in sanitized form so predicted and observed success can be calibrated.

## Training data

Production telemetry MUST NOT be treated as sufficient counterfactual ground truth.

A learned router release MUST be evaluated using comparative offline data such as LocdexBench and/or explicit research datasets before promotion.

Verification outcomes SHOULD be primary training labels.

## Private backend

The ingestion/training backend MUST live outside the public repository.

Initial private deployment SHOULD use:

- Cloudflare Worker for ingestion;
- Analytics Engine for recent operational metrics;
- R2 for canonical long-term sanitized data.

The Worker MUST reject oversized or unknown-schema batches and MUST NOT persist transport identifiers such as request IPs into the routing dataset.

Queues/ClickHouse are deferred until operational scale requires them.

## Enterprise boundary

Public Locdex exposes only extension contracts.

Private enterprise implementations may tighten policy or redirect supported integrations, but MUST NOT weaken native OSS security invariants.

Dependency direction is:

```text
locdex-enterprise → locdex
```

never the reverse.

## Package gate

Before runtime/model qualification:

```bash
python -m pip install -e ".[dev]"
python scripts/preflight.py
```

Preflight MUST compile source/tests, strictly import all package modules, collect/run tests, build the wheel, verify required wheel contents, install it into a temporary environment, and start packaged `locdex --help`.

Only after the package gate is green should hardware/runtime, Qwen, Kimi, agent tools, Git, cloud providers, telemetry backend, LocdexBench, and OS/hardware matrix qualification begin.


## v3.3 interaction, sandbox, orchestration, escalation

- `locdex` MUST remain the primary persistent interactive interface; `locdex task` remains the headless primitive.
- The interactive console MUST keep stdin ownership outside the agent worker so steering, cancellation, and approvals can coexist.
- Sandbox capability reporting MUST distinguish process, filesystem, and network isolation. It MUST NOT market logical policy as native OS isolation.
- The Windows native helper MAY strengthen isolation incrementally, but unsupported capability flags MUST remain false.
- Multi-agent dependencies MUST fail closed: failed prerequisites block downstream execution and conflicting prerequisite changes MUST NOT be silently merged.
- Locdex MUST NOT auto-commit or auto-merge multi-agent changes without explicit user intent.
- Cloud fallback MUST be opt-in, provider-configured, network-policy-gated, and use the same Locdex tool/permission/sandbox/verification stack as local execution.
- Escalation context SHOULD be minimal and evidence-driven; raw repository dumps are forbidden as a default handoff.
- Telemetry collection MUST never be required for routing or task execution.
- Router training in the public client MUST be offline and operate only on the allow-listed sanitized schema.
