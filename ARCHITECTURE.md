# Locdex Architecture v3.3

Locdex is a local-first coding-agent runtime. The model is replaceable infrastructure; Locdex owns repository intelligence, context construction, security, routing, tools, verification, telemetry, and hardware policy.

The governing principle is:

> Send the minimum sufficient context, not the maximum available context.

## System

```text
CLI / future IDE adapters
        ↓
Agent Orchestrator
UNDERSTAND → RETRIEVE → PLAN? → ACT → VERIFY → REVIEW → DONE
                                      ↘ DIAGNOSE → RETRY
        ↓
Repository Intelligence
repo map / symbols / imports / references / tests / git state / fingerprints
        ↓
Context Compiler
ranking / token budget / exact-source extraction / compression / dedupe / cache planning
        ├──────────── Local Context Path ─────────────┐
        └──────────── Cloud Context Gateway ─────────┤
                    secrets / privacy / hard budgets │
                    progressive disclosure / ledger │
                                                    ↓
Execution Planner + Model Router
quality / privacy / cost / latency / hardware / capability
        ↓
Cost Controller
        ↓
Providers / Local Runtime
        ↓
Tool Engine + Verification Engine
        ↓
Local metrics + opt-in shared telemetry
```

## Local models

- `qwen`: Qwen3.5 35B-A3B Q4_K_S, supported/default, 32 GB-class target.
- `kimi`: Qwen3.5 9B Kimi-K3 Distilled Q4_K_M, experimental, ~16 GB-class target.

The `kimi` key is intentionally preserved for the planned 9B Kimi-K3 distillation.

## Repository Intelligence vs Context

`intelligence/` answers “what do we know about this repository?”

`context/` answers “what is the smallest representation of that knowledge this task/model should receive?”

Cloud models never receive direct filesystem access. They receive bounded context packs; additional context is retrieved locally by Locdex and disclosed progressively.

## Routing v0 → learned local router

Routing is local. The launch router is deterministic `rules-v0`.

A task fingerprint contains structured metadata such as task class, language, repo-size bucket, file fanout, test/stack-trace presence, context estimate, complexity, tool intensity, attempt number, and previous-model failure.

Hard policy filters run before model ranking:

- privacy/local-only constraints;
- provider allow-list;
- model/hardware availability;
- context requirements;
- cost and latency ceilings.

The router predicts separately for each model:

- probability of success;
- estimated cost;
- estimated latency;
- expected attempts.

Session-aware switching penalties keep a healthy tool loop on the current model. Reconsideration happens at meaningful boundaries such as a new task, runtime failure, or verification failure.

Later learned artifacts are versioned, checksum-verified, run locally, and fall back to `rules-v0` if absent or invalid. Locdex does not call a central routing service for every task.

## Telemetry learning loop

Shared telemetry is OFF by default.

Consent modes:

- OFF — no shared telemetry.
- BASIC — sanitized routing/outcome metadata only.
- RESEARCH — separate explicit research consent; it does not silently trigger shadow-model evaluation.

BASIC telemetry must not contain source code, prompts, model responses, diffs, filenames/paths, repository identity, branch identity, credentials, environment values, company/user identity, or persistent installation/device identifiers.

Production telemetry is selection-biased, so it is not sufficient by itself to train the router. Router training combines:

1. sanitized production outcomes;
2. LocdexBench comparative runs across models;
3. explicit research/evaluation datasets.

The verifier provides objective labels: compile, tests, lint, validation, escalation, and revert outcomes.

## Private telemetry infrastructure

The public repository contains only the client schema, sanitizer, queue, uploader, router runtime, and training contracts.

The private backend target is:

```text
Locdex clients
  ↓ sanitized batches
Cloudflare Worker
  ├─ strict schema / size / rate checks
  ├─ Analytics Engine for recent operational metrics
  └─ R2 for canonical sanitized long-term data
        ↓
LocdexBench + offline cleaner/evaluator
        ↓
router trainer
        ↓
versioned router artifact
        ↓
Locdex clients
```

Cloudflare Queues and ClickHouse are deferred until scale justifies them.

## Security

Native security remains public and available to every user:

- workspace/path boundaries;
- command policy;
- explicit Git mutation intent;
- secret redaction;
- cloud context policy;
- tool risk classes;
- deterministic verification.

Enterprise implementation code is not in this repository. The OSS repo contains only extension contracts under `src/locdex/extensions/`. A private `locdex-enterprise` package may add SSO/RBAC, hardened sandboxes, central policy, audit/SIEM integrations, enterprise secret brokers, egress controls, approved-model policy, internal inference, and air-gap support.

The private package depends on public Locdex; public Locdex never depends on the private package.


## v3.3 execution architecture

### Interactive console

`locdex` is the primary human interface. The active agent executes on a worker thread while the terminal event loop owns stdin. The console multiplexes three inputs without a second terminal:

- user steering text;
- `/cancel` and `/status`;
- permission decisions.

The persistent steering queue remains the transport boundary, so future TUI/IDE clients can submit the same events.

### Windows native sandbox

The Windows backend has a native Rust helper contract:

```text
Python SandboxPolicy
      ↓
locdex-windows-sandbox.exe
      ├─ restricted access token
      ├─ Job Object
      └─ kill-on-close process containment
```

Capability reporting is strict. Process isolation is reported independently from filesystem and network isolation. The current helper does not claim native filesystem ACL or network isolation; those restrictions remain enforced by Locdex policy until a stronger helper revision ships.

### Dependency-aware multi-agent supervisor

Agent specs may declare `depends_on`, `priority`, and `role`. Ready agents may run in parallel. Successful prerequisite workspace changes are inherited into downstream worktrees without commits. Failed prerequisites block dependents. Conflicting prerequisite edits block execution, and final overlapping files are surfaced in an integration plan. Locdex does not auto-commit or auto-merge.

### Local-first cloud escalation

The execution path is:

```text
task
 ↓
local AgentEngine
 ↓ failure / escalation / failed verification
rollback incomplete Locdex edits
 ↓
bounded failure/evidence handoff
 ↓
user-configured OpenAI-compatible provider
 ↓
same tool / permission / sandbox / verifier stack
```

Cloud fallback requires explicit configuration and a network-enabled sandbox. Locdex does not hard-code a default provider.

### Telemetry → offline router artifact

When shared telemetry is opted in, completed local/cloud attempts emit only the existing allow-listed routing outcome schema. The public client can convert exported sanitized events into a versioned lookup artifact with `locdex router train`. Training remains offline; no client performs online model/router training.
