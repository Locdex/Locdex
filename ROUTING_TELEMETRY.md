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

BASIC telemetry is enabled by default with visible first-use notice and one-command opt-out. Events queue locally and upload automatically after tasks only when a valid HTTPS endpoint is configured. `locdex telemetry disable` clears unsent events; RESEARCH still requires separate opt-in.

## Data sources for router releases

A new router artifact must not be trained from production telemetry alone. The training corpus should combine:

1. production sanitized outcomes;
2. LocdexBench comparative runs across available models;
3. explicit research datasets/evaluations.

This prevents the router from merely learning its own previous selection policy.

## Backend separation

The public repo now includes an auditable, open-source Cloudflare Worker starter under `infra/telemetry-worker/`. It provides a write-only `POST /v1/events` endpoint, strict v1 validation, Cloudflare rate limiting, R2 canonical sanitized batches, and Analytics Engine projections. No Cloudflare account secret or admin token is stored in the client or Git repository. Private operational infrastructure and training pipelines stay outside the public repo. The Worker must be deployed to a real account and its resulting HTTPS URL configured before launch clients can upload.

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


## Adaptive timeout and cloud escalation on native inference failure

In interactive sessions, a local model runs inside an isolated process. Model-load and generation deadlines are calculated separately from model size, detected CPU/RAM/GPU resources, context/output size, and locally observed token throughput. Calibration is saved locally in `inference/speed-v1.json` under Locdex's cache directory and contains only per-model/backend speed metrics. No user ID or source material is recorded.

A model timeout is converted to a failed local attempt after the hardened change journal rolls back agent-owned edits. The usual cloud escalation policy is then applied: cloud must be explicitly enabled and configured, network access must be allowed by the sandbox, and the task must not have been cancelled. If no cloud service is configured (or the sandbox blocks networking), the CLI reports the local timeout without hanging. An explicit `LOCDEX_INFERENCE_TIMEOUT_SECONDS` overrides both estimated deadlines. Query local estimates using `locdex inference budget --model smoke`.

## Named provider adapters

`locdex cloud providers` lists supported native Anthropic and Chat Completions-compatible providers. The local-first router keeps provider use behind explicit cloud configuration and a network-enabled sandbox. A native Anthropic Messages tool-use adapter returns the Locdex action object; the OpenAI-compatible adapter uses JSON Schema output with a carefully bounded JSON-only fallback for providers lacking strict schema support. Provider-specific API keys are environment-only and never uploaded through telemetry.

## Publishing real benchmark results

A single calculator qualification probe is not a robust benchmark. The public repository includes a safe exporter for qualification records and `benchmarks/README.md` with rules for methodology, controlled tasks, multiple seeds, failure reporting and eventual Hugging Face distribution. Do not treat anonymized production routing telemetry as comparative benchmark scores.
