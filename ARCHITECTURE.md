# Locdex v1.4 Architecture — Stable Release in Development

**Release status:** The existing stable release is **v1.3.1**. The published **v1.4.0a1** prerelease is a testing build of this **same v1.4 architecture**. Stable **v1.4.0** is still under development; it is not yet shipped. See [v1.4 release gates](docs/V1_4_STABLE_ROADMAP.md).

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

## Agent vs model runtime boundary

These are **two internal layers of the v1.4 architecture**, not a v1.4 alpha versus stable split. The **agent architecture** owns session state, repository intelligence, context assembly, permissions, sandbox policy, tools, verification, rollback and routing. The **model runtime architecture** only owns the model execution boundary: local GGUF installation/backends and inference, or user-authorized cloud provider calls. Tool authorization never comes from model output alone.

```text
AGENT: user -> session -> policy -> repo/context -> agent/router -> guarded tools
                                             ^                         |
                                             +------ verifier/journal <-+
                              |
                              +---- model interface ----+
                                                        |
RUNTIME:                           local profiles -> hardware -> llama.cpp worker
                                   OR configured cloud adapter (opt-in)
                                                        |
                                              model response -> agent
```

For a visually separated, component-level view, see [README: Two architectural layers, one v1.4 release](README.md#two-architectural-layers-one-v14-release). For end-user installation, see [local-model quickstart](docs/QUICKSTART_LOCAL_MODELS.md).

## Local models

Model metadata lives in `src/locdex/models/profiles.py`, not in the agent orchestration layer. The default supported 32 GB-class profile is `qwen` (Qwen3.5 35B-A3B Q4_K_S). Additional options include `smoke` (Qwen2.5-Coder 1.5B, development only), `qwen25-3b`, `qwen25-7b`, `qwen25-14b`, `kimi`, `deepseek-lite` and `qwen3-coder` with varying experimental/qualification statuses. Refer to `locdex model list` for current RAM guidance and installation state.

The runtime detects hardware, installs compatible prebuilt llama.cpp backends when available, manages local GGUF files and uses an isolated killable worker for interactive local inference and qualification. Load/generation timeout estimation is adaptive and saved calibration metadata is local to the user's machine. Cloud inference is a separate opt-in provider adapter, not the local inference runtime.

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

BASIC telemetry is enabled by default with a visible first-run notice and opt-out; **no network request occurs unless a real telemetry HTTPS endpoint is configured**. RESEARCH mode requires separate explicit opt-in. The code in `src/locdex/telemetry/settings.py` is the source of truth for consent defaults.

Consent modes:

- OFF — no telemetry uploads and no pending event queue.
- BASIC — sanitized routing/outcome metadata only (default; endpoint must be configured to upload).
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


## v1.4 execution architecture

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
