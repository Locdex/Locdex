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

Locdex exposes a local model catalog across hardware tiers. `locdex model list` shows install state, approximate model size, minimum RAM, and recommended RAM.

- `smoke` — Qwen2.5-Coder 1.5B Q4_K_M, development-only runtime/agent smoke profile.
- `qwen25-3b` — Qwen2.5-Coder 3B Q4_K_M, experimental, 8 GB-class target.
- `qwen25-7b` — Qwen2.5-Coder 7B Q4_K_M, supported, 8–12 GB-class target.
- `kimi` — Qwen3.5 9B Kimi-K3 Distilled Q4_K_M, experimental, 16 GB-class target.
- `qwen25-14b` — Qwen2.5-Coder 14B Q4_K_M, supported, 16 GB-class target.
- `deepseek-lite` — DeepSeek-Coder-V2-Lite Instruct Q4_K_M, experimental, 16–20 GB-class target.
- `qwen3-coder` — Qwen3-Coder 30B-A3B Instruct Q4_K_M, experimental, 24–32 GB-class target.
- `qwen` — Qwen3.5 35B-A3B Q4_K_S, supported/default, 32 GB-class target.

Users select models explicitly with `locdex model use <key>` or per task with `locdex task --model <key> ...`. The smoke profile is intentionally not a production recommendation.

## npm installation

Locdex remains a Python runtime, but developers can use the npm wrapper as the distribution entry point:

```bash
npm install -g @locdex/cli
locdex --version
```

The npm package creates a Locdex-owned Python environment and forwards the `locdex` command to the Python core. It does not automatically download models or install the llama.cpp backend. Those remain explicit:

```bash
locdex runtime install --backend auto
locdex model list
locdex model install qwen25-7b
locdex model use qwen25-7b
```

The npm wrapper requires Node.js 18+ and Python 3.10–3.12 in its first release. A fully managed Python bootstrap can replace that host-Python requirement later without changing the Python core.

## User-defined multi-agent runs

Locdex does not impose fixed planner/coder/reviewer roles. Users define each agent's name, task, model, step budget, routing mode, and optional write scope in YAML.

```yaml
version: 1

defaults:
  model: qwen25-7b
  max_steps: 8
  mode: balanced

agents:
  - name: backend
    task: Implement the API migration without changing frontend code.
    write_scope:
      - src/backend/**

  - name: frontend
    task: Update the frontend client for the new API.
    model: qwen25-3b
    write_scope:
      - src/frontend/**
```

Validate and run it with:

```bash
locdex agents validate --config agents.yaml
locdex agents run --config agents.yaml --repo . --parallel 2
```

Each agent receives an isolated Git worktree and branch. Locdex does not auto-commit or auto-merge agent changes. Multi-agent runs currently require a clean base working tree. Parallelism defaults to 1 so local users do not accidentally load several models into RAM; raising `--parallel` is an explicit user choice.

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
