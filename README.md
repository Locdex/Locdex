# Locdex

Locdex is a local-first coding-agent runtime built around four constraints: minimum sufficient context, explicit security boundaries, replaceable models, and transparent routing/cost policy.

## Start here

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/preflight.py
```

Then inspect the baseline:

```bash
locdex status
locdex models
locdex prepare --task "inspect the repository and explain the CLI entry point"
```

The `prepare` command exercises the new Repository Intelligence → Context Compiler → Routing path without downloading a model yet.

## Model profiles

- `qwen` — Qwen3.5 35B-A3B Q4_K_S, supported/default, 32 GB-class target.
- `kimi` — Qwen3.5 9B Kimi-K3 Distilled Q4_K_M, experimental, ~16 GB-class target.

Kimi is the same lower-memory profile previously selected for Locdex.

## Architecture

```text
CLI
 ↓
Agent Orchestrator
 ↓
Repository Intelligence
 ↓
Context Compiler
 ├─ local context
 └─ Cloud Context Gateway
 ↓
Execution Planner / Model Router
 ↓
Providers / local runtime
 ↓
Tools + Verification
```

Normal-user security is part of the public repo. Enterprise implementations are not. The public package contains only the enterprise extension contracts under `src/locdex/extensions/`.

See `ARCHITECTURE.md` and `BUILD_SPEC.md`.


## Routing v0 → learned local router

Locdex routing is a local subsystem. It profiles the task into structured features such as task class, language, repository-size bucket, estimated file fanout, context size, test/stack-trace presence, complexity, tool intensity, attempt number, and previous-model failure.

The router applies hard policy constraints first (privacy, provider allow-list, hardware/model availability, cost/latency ceilings), then predicts per-model success/cost/latency. The launch scorer is inspectable rules (`rules-v0`). A versioned learned artifact can later replace those priors without changing the routing API.

```bash
locdex route --task "fix the failing refresh-token test" --repo .
locdex router status
locdex router update --manifest-url <router-release-manifest>
```

Router artifacts run locally. Locdex does not call a central service on every task to ask which model to use.

## Shared routing telemetry

Shared telemetry is **off by default**. Consent modes are OFF, BASIC, and separately explicit RESEARCH. BASIC telemetry contains sanitized task/model/outcome features only. It excludes raw prompts, code, diffs, filenames/paths, repository identity, model responses, credentials, company/user identity, and persistent installation IDs.

```bash
locdex telemetry status
locdex telemetry preview
locdex telemetry endpoint https://telemetry.locdex.dev/v1/events
locdex telemetry enable
locdex telemetry flush
```

Events queue locally and upload in batches only when telemetry is enabled **and** an endpoint is configured. The public Locdex repo contains the client schema/sanitizer/batching logic; the ingestion/data-lake/training service lives in a separate private infrastructure repository.

Production telemetry measures the model Locdex actually selected. Comparative/counterfactual training data must come primarily from LocdexBench and other explicit offline/opt-in evaluations, not from silently running extra models on private repositories.
