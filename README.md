# Locdex

Locdex is a local-first coding-agent runtime with replaceable local models, repository intelligence, bounded context, explicit permissions, verification, rollback, and optional cloud escalation.

## Install Locdex

Choose either npm or pip. They install the same Locdex Python core.

### npm

```bash
npm install -g @locdex/cli
locdex --version
```

The npm package is a lightweight launcher. It creates a Locdex-owned Python environment and forwards the `locdex` command to the Python runtime.

Requirements for the first npm release:

- Node.js 18+
- Python 3.10, 3.11, or 3.12

### pip

```bash
python -m pip install locdex
locdex --version
```

> Registry installs work after the matching releases are published to npm and PyPI. If you are developing Locdex from this repository before release, use the **Development** section at the bottom of this README.

## First-time setup

Locdex does not silently download a model or install a compute backend.

Inspect your hardware:

```bash
locdex status
```

Install the local inference runtime:

```bash
locdex runtime install --backend auto
locdex runtime verify
```

See models that fit different hardware tiers:

```bash
locdex model list
```

Install and select one explicitly:

```bash
locdex model install qwen25-7b
locdex model use qwen25-7b
```

Then run Locdex inside a project:

```bash
cd my-project
locdex task --task "Fix the failing authentication refresh test."
```

## Permissions and code review

Locdex separates model decisions from runtime permission decisions. A model can request an action, but it cannot approve its own access.

The default CLI mode is `ask`. Read-only repository inspection proceeds automatically. Before a write, command, or Git mutation, Locdex can show the proposed action and ask you to allow it once, allow similar actions for the current session, or deny it.

Example:

```text
Permission required: write | replace_symbol
------------------------------------------------------------------------
--- a/src/auth/token.py::refresh
+++ b/src/auth/token.py::refresh
-    if token.expiry < now:
+    if token.expiry <= now:
         refresh(token)
------------------------------------------------------------------------
[y] allow once   [a] allow similar actions this session   [n] deny
```

Permission modes:

| Mode | Behaviour |
| --- | --- |
| `plan` | Read/search only. Mutating actions are denied. |
| `ask` | Default. Reads are automatic; writes, commands, network/Git-class actions require approval. |
| `auto-edit` | Workspace edits are automatic; commands and Git-class actions still require approval. |
| `trusted` | Reads, workspace edits, and normal execution are automatic; Git/network-class actions still require approval. |
| `unrestricted` | Allows all non-dangerous actions permitted by the native Locdex policy. |

Choose a mode per task:

```bash
locdex task \
  --permission-mode ask \
  --task "Refactor the authentication service and run the relevant tests."
```

For CI or machine-readable runs, do not use interactive `ask` mode:

```bash
locdex task \
  --json \
  --permission-mode plan \
  --task "Inspect this repository and report what should change."
```

Native Locdex security rules remain in force underneath permission modes. Dangerous operations stay blocked, workspace boundaries are enforced, Git writes still require explicit task intent, failed/incomplete agent runs roll back Locdex-owned mutations, and tests are protected from opportunistic rewriting unless the user explicitly asks to change them.

## Model profiles

`locdex model list` shows install state, approximate model size, minimum RAM, recommended RAM, and qualification status.

- `smoke` — Qwen2.5-Coder 1.5B Q4_K_M, development-only.
- `qwen25-3b` — Qwen2.5-Coder 3B Q4_K_M, experimental, ~8 GB-class.
- `qwen25-7b` — Qwen2.5-Coder 7B Q4_K_M, qualification candidate, 8–12 GB-class.
- `kimi` — Qwen3.5 9B Kimi-K3 Distilled Q4_K_M, experimental, ~16 GB-class.
- `qwen25-14b` — Qwen2.5-Coder 14B Q4_K_M, qualification candidate, ~16 GB-class.
- `deepseek-lite` — DeepSeek-Coder-V2-Lite Instruct Q4_K_M, experimental, 16–20 GB-class.
- `qwen3-coder` — Qwen3-Coder 30B-A3B Instruct Q4_K_M, experimental, 24–32 GB-class.
- `qwen` — Qwen3.5 35B-A3B Q4_K_S, supported/default, ~32 GB-class.

Select models globally:

```bash
locdex model use qwen25-7b
```

Or choose one for a task:

```bash
locdex task --model qwen25-7b --task "Fix the parser bug."
```

The `smoke` profile exists to validate Locdex mechanics on small hardware. It is not a production coding recommendation.

## Model qualification

Catalog labels are not a substitute for real hardware results. Locdex includes a reproducible local qualification command:

```bash
locdex model qualify qwen25-7b
```

Qualification checks:

- hardware eligibility
- runtime health
- a deterministic inference probe
- a bounded coding-agent task
- structured verification
- rollback/test-preservation behaviour

Use a lighter inference-only check with:

```bash
locdex model qualify qwen25-7b --prompt-only
```

Qualification reports are stored in the Locdex user cache and contain outcome/runtime/hardware metadata, not the user's repository code.

## User-defined multi-agent runs

Locdex does not impose planner/coder/reviewer roles. You define each agent's name, task, model, step budget, routing mode, and write scope.

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

Validate and run:

```bash
locdex agents validate --config agents.yaml
locdex agents run --config agents.yaml --repo . --parallel 2
```

Each agent receives an isolated Git worktree and branch. Locdex does not auto-commit or auto-merge agent changes. Multi-agent runs currently require a clean base working tree. Parallelism defaults to 1 so local users do not accidentally load several large models into RAM.

## Repository intelligence and context

Locdex retrieves repository structure before asking a model to rediscover it. The runtime can build symbol/import/test relationships, detect missing local symbols, retrieve exact source ranges, and compile a bounded Context Pack.

Long sessions use durable `TaskState` plus deterministic context compaction:

```text
stable system rules
        +
durable task state
        +
recent working context
        +
retrievable repository/source context
```

Exact source can be discarded when stale and reread when needed instead of being carried indefinitely through local or cloud prompts.

## Routing and telemetry

Routing runs locally. Locdex profiles the task, applies policy/hardware constraints, then chooses among available models.

```bash
locdex route --task "fix the failing refresh-token test" --repo .
locdex router status
```

Shared routing telemetry is **off by default**. BASIC telemetry contains sanitized task/model/outcome features and excludes raw prompts, code, diffs, filenames/paths, repository identity, model responses, credentials, and persistent user/install identity.

```bash
locdex telemetry status
locdex telemetry preview
locdex telemetry enable
locdex telemetry flush
```

## Architecture

```text
CLI / future IDE surfaces
        ↓
Permission + policy layer
        ↓
Agent orchestrator
        ↓
Repository intelligence
        ↓
Context compiler / TaskState
        ↓
Execution planner + model router
        ↓
Local models / optional cloud providers
        ↓
Tool executor
        ↓
Change journal + verification
```

Normal-user security belongs in the public Locdex repository. Enterprise implementations can extend the public contracts with organizational policy, identity, audit, secret-management, sandbox, and inference-control integrations.

See `ARCHITECTURE.md` and `BUILD_SPEC.md`.

## Development

The following setup is for contributors working on Locdex itself. It is **not** the normal user installation path.

Clone the repository, then create a development environment:

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/preflight.py
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/preflight.py
```

The editable `.[dev]` install and `scripts/preflight.py` are contributor workflows used to run the test/lint/package gates before changes are merged.
