# Locdex Routing + Telemetry v0

## What is implemented now

### Router

- hard policy layer (`local_only`, cloud allow-list, cost/latency ceilings)
- structured `TaskProfile`
- structured `RoutingModelProfile`
- model-specific success/cost/latency predictions
- balanced / fast / quality / local-only decision modes
- session switching penalty
- verification/runtime failure escalation boundaries
- built-in `rules-v0` scorer
- versioned local router artifact loader/updater
- dependency-free learned lookup artifact scorer
- calibration/training contracts

### Shared telemetry

Consent modes:

- `OFF` — no upload
- `BASIC` — sanitized routing-performance outcomes only
- `RESEARCH` — separate explicit consent state reserved for comparative evaluation; no silent shadow-model execution is implemented

BASIC telemetry may contain task taxonomy/features, model/quant/backend buckets, token counts, latency, tool/edit counts, verifier booleans, cost, selected route, and calibrated router predictions.

It must not contain source code, prompts, model responses, file names/paths, repository/branch identity, environment variables, API keys/secrets, company/user identity, or persistent installation/device identifiers.

Events queue locally and upload only if telemetry is enabled and an endpoint is configured.

## Data sources for router releases

A new router artifact must not be trained from production telemetry alone. The training corpus should combine:

1. production sanitized outcomes;
2. LocdexBench comparative runs across available models;
3. explicit research datasets/evaluations.

This prevents the router from merely learning its own previous selection policy.

## Backend separation

The public repo contains the client schema, sanitizer, queue, router and artifact runtime. Cloudflare ingestion, R2/Analytics Engine storage, dataset processing and router training live in the private infrastructure repository.

## Commands

```bash
locdex route --task "fix the failing refresh token test" --repo .
locdex router status
locdex router update --manifest-url <url>

locdex telemetry status
locdex telemetry preview
locdex telemetry endpoint https://telemetry.locdex.dev/v1/events
locdex telemetry enable       # BASIC
locdex telemetry research     # separate RESEARCH consent
locdex telemetry disable
```


## v3.3 local-first escalation

A coding task now has an execution wrapper around the AgentEngine. The local selected model attempts the task first. An `escalate`, `incomplete`, runtime-error, or failed-verification result may be reconsidered only when:

1. the user explicitly configured a cloud provider/model;
2. the active sandbox permits network access;
3. the task was not cancelled.

The cloud adapter is OpenAI-compatible and provider-neutral. It receives a bounded local-attempt handoff plus context compiled/retrieved by Locdex; it does not receive direct filesystem access.

Inspect configuration without revealing the key:

```bash
locdex cloud status
```

## v3.3 outcome recording and offline training

When telemetry is opted in, local and cloud attempts use the same allow-listed `routing_outcome` event. Cost/token/latency fields are populated when a provider exposes them. Telemetry failure must not become an agent failure.

Exported sanitized JSON or JSONL can be transformed into a local lookup artifact:

```bash
locdex router train \
  --input routing-events.jsonl \
  --output router.json
```

The trainer groups outcomes by task class and model and emits success rate, average cost, latency, and attempts. This is an offline artifact-building step, not online learning on user machines.
