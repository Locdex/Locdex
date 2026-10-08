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
locdex
```

Running `locdex` opens a persistent interactive session. For scripts/CI, the bounded one-shot command remains available:

```bash
locdex task --task "Fix the failing authentication refresh test."
```

## Permissions and code review

Locdex separates model decisions from runtime permission decisions. A model can request an action, but it cannot approve its own access.

The default CLI mode is `ask`. Read-only repository inspection proceeds automatically. Before a write, command, or Git mutation, Locdex can show the proposed action and ask you to allow it once, allow similar actions for the current session, or deny it.

Permission prompts are compact by default so large repositories do not flood the terminal:

```text
Allow Locdex to edit src/auth/token.py?
[y] once  [a] similar this session  [d] details  [N] deny
```

Press `d` only when you want the bounded command/diff details. Permission previews are intentionally capped and are built from the requested operation rather than dumping an entire target file.

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

## Interactive sessions

The normal Locdex experience is a persistent repository session:

```text
Locdex interactive
Session: 7d6c8a13d4ef
Repository: /workspace/project
Model: qwen25-7b
Permissions: ask
Sandbox: workspace-write

locdex> Fix the refresh-token bug.
```

Session state stores task summaries, durable user notes, permission/sandbox choices, the latest ChangeSet diff, and local checkpoint references. Exact source is re-read from the repository rather than copied indefinitely into session history.

Useful commands:

```text
/help
/status
/model qwen25-14b
/permissions ask
/sandbox workspace-write
/diff
/checkpoints
/undo
/sessions
/note Do not modify migrations.
/compact
/new
/exit
```

Resume the latest session for a repository:

```bash
locdex resume
```

Or a specific session:

```bash
locdex resume <session-id>
```

During agent runs, Locdex shows an animated live status line (elapsed time, step count, and completed tool count) plus a concise event-driven activity log for file reads/edits, commands, tests, and permission outcomes. The spinner indicates an active worker even during model generation; it is NOT a fabricated percentage-complete estimate. While an agent task is running, the same interactive terminal remains usable. Type ordinary text to steer the active run, use `/status` to inspect policy, or `/cancel` to cancel and roll back incomplete Locdex-owned changes. Permission prompts are multiplexed through the same console instead of competing for stdin.

Typing `exit`, `quit`, `/exit`, or `/quit` at an idle Locdex prompt now closes the chat. During an active task, those commands request cancellation and then close the chat once the running operation stops. `/cancel` or Ctrl+C requests cancellation and preserves normal rollback; if a native model/runtime call is completely stuck, press Ctrl+C **again** within four seconds (with a short gap) for emergency process termination. Emergency termination cannot guarantee rollback or completion of cleanup. Approval prompts share the same active input loop rather than cancelling and recreating terminal input.\n\nCross-terminal steering remains available for automation or a second shell:

```bash
locdex steer <session-id> "Do not touch migrations; keep the fix inside src/auth."
locdex cancel <session-id>
```

Completed tasks that changed files create a local checkpoint. `/undo` restores only the files Locdex changed and refuses to overwrite files that have diverged since the checkpoint.

## Sandboxing

Permissions and sandboxing are separate controls:

- **permissions** decide whether the user authorized an action;
- **sandboxing** limits what the process can actually access even after approval.

Sandbox modes:

| Mode | Workspace | Commands | Network / remote Git |
| --- | --- | --- | --- |
| `read-only` | read only | blocked | blocked |
| `workspace-write` | writable | allowed | blocked |
| `workspace-network` | writable | allowed | allowed subject to permissions |
| `unrestricted` | native Locdex policy | allowed | allowed subject to permissions |

The default is `workspace-write`.

Inspect the sandbox backend on your machine:

```bash
locdex sandbox status
locdex sandbox modes
```

On Linux, if `bubblewrap` is installed, Locdex runs development commands inside an OS filesystem sandbox and uses a separate network namespace when network access is disabled.

On Windows, Locdex now supports a native Rust helper. When installed, commands run with a restricted Windows token and Job Object process-tree containment. `locdex sandbox status` reports this as `windows-native`. Native filesystem ACL isolation and native network isolation are **not** claimed yet; workspace/network restrictions continue to be enforced by Locdex policy until those helper capabilities are implemented. Without the helper, Windows reports the `logical` backend.

Choose a sandbox for one-shot tasks:

```bash
locdex task \
  --sandbox workspace-write \
  --permission-mode ask \
  --task "Fix the parser and run its tests."
```

## Project instructions and local skills

Locdex automatically reads repository guidance from:

```text
AGENTS.md
LOCDEX.md
.locdex/instructions.md
.locdex/skills/*.md
```

These instructions are injected before the current task, below native Locdex safety policy. This lets projects persist conventions such as package manager choice, protected directories, required tests, release workflows, and repository-specific procedures.

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

Locdex does not impose planner/coder/reviewer roles. You define each agent's name, role, task, model, step budget, routing mode, write scope, priority, and dependencies.

```yaml
version: 1

defaults:
  model: qwen25-7b
  max_steps: 8
  mode: balanced
  permission_mode: auto-edit
  sandbox_mode: workspace-network

agents:
  - name: backend
    task: Implement the API migration without changing frontend code.
    write_scope:
      - src/backend/**

  - name: frontend
    role: client
    task: Update the frontend client for the new API.
    model: qwen25-3b
    depends_on:
      - backend
    priority: 10
    write_scope:
      - src/frontend/**
```

Validate and run:

```bash
locdex agents validate --config agents.yaml
locdex agents run --config agents.yaml --repo . --parallel 2
```

Each agent receives an isolated Git worktree and branch. Agents whose dependencies are complete inherit those dependency workspace changes without creating commits. Failed dependencies block downstream agents; conflicting prerequisite edits block the dependent agent; and final overlapping changed files are reported in an integration plan. Locdex still does not auto-commit or auto-merge final changes. Multi-agent runs require a clean base working tree. Parallelism defaults to 1 so local users do not accidentally load several large models into RAM.

Each agent can set its own `permission_mode`. Interactive `ask` mode is supported for serial runs (`--parallel 1`). Parallel runs require non-interactive policies such as `plan`, `auto-edit`, `trusted`, or `unrestricted` so approval prompts cannot collide across worker threads.

## MCP tools

MCP support is optional:

```bash
python -m pip install "locdex[mcp]"
```

Configure local stdio servers in `.locdex/mcp.json`:

```json
{
  "servers": {
    "docs": {
      "command": "python",
      "args": ["tools/docs_server.py"],
      "env": {}
    }
  }
}
```

Inspect configured servers:

```bash
locdex mcp list
```

Locdex exposes MCP to the agent through two auditable tools: `mcp_list_tools` and `mcp_call`. MCP calls are classified as network/external actions: the default `workspace-write` sandbox blocks them. A user must opt into a network-enabled sandbox and normal permission approval still applies. The stdio server process is wrapped by the active OS sandbox backend when one is available.

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

BASIC routing telemetry is **on by default**, with a visible first-run notice and an immediate opt-out: `locdex telemetry disable` (which also clears pending events). It contains strictly allow-listed task/model/outcome features and excludes prompts, code, diffs, paths, repository identity, responses, secrets and persistent installation IDs. No network request is made until you configure a real HTTPS endpoint. When configured, Locdex attempts to upload a small batch after each task; failures do not interrupt coding. RESEARCH telemetry remains separately opt-in.

```bash
locdex telemetry status
locdex telemetry preview
locdex telemetry enable
locdex telemetry disable
locdex telemetry endpoint https://YOUR-DEPLOYED-WORKER.workers.dev/v1/events
locdex telemetry flush
```

## Architecture

```text
Interactive CLI / future IDE surfaces
        ↓
Session manager + event stream + checkpoints
        ↓
Permission policy
        ↓
Sandbox policy / OS sandbox backend
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


## Configured cloud fallback

Cloud fallback is explicit and disabled unless the user configures it. Locdex uses an OpenAI-compatible chat-completions endpoint rather than hard-coding a provider.

```bash
export LOCDEX_CLOUD_ENABLED=1
export LOCDEX_CLOUD_PROVIDER=my-provider
export LOCDEX_CLOUD_MODEL=my-model
export LOCDEX_CLOUD_BASE_URL=https://provider.example/v1
export LOCDEX_CLOUD_API_KEY=...
locdex cloud status
```

Use `workspace-network` when cloud escalation is allowed:

```bash
locdex task --sandbox workspace-network --task "Fix the failing parser."
```

The local attempt remains first. If it cannot complete, Locdex rolls back incomplete Locdex-owned edits, builds a bounded handoff containing failure/verification metadata rather than the whole repository, and retries through the configured cloud session. Exact source is still retrieved through Locdex tools.

Router training is offline:

```bash
locdex router train --input routing-events.jsonl --output router.json
```

The trainer consumes the sanitized routing-event schema and produces the same versioned lookup artifact used by the local router. Shared telemetry remains opt-in and does not perform online training.


## Installation progress

`locdex model install <model>` displays the model-download byte percentage, transfer rate and estimated time remaining when the remote server reports a content length. Once downloaded, a separate checksum-verification bar tracks bytes checked; there is no misleading combined-install percentage. `locdex runtime install --backend auto` shows the pip wheel download progress and an explicit backend-verification step. Package installation from npm is reported in stages and can be made fully visible with `npm install -g @locdex/cli --foreground-scripts --loglevel=info`.


Multi-agent runs support up to 16 agents in one config, up to 8 concurrent workers (`--parallel 8`), and default to 1. Interactive `ask` permissions require `--parallel 1`; parallel agents use isolated worktrees and a non-interactive permission policy. Keep concurrency low for large RAM-hungry local models.

## Live terminal dashboard and bounded local inference

Active interactive tasks render a live status header **above** the input rather than a bottom toolbar. It shows elapsed time, actual 1/12 step progress, up to four recent events, and the current model/operation phase. A permission request is always shown together with the short request description and explicitly labeled controls:

```text
  ┌─ Permission required ───────────────────────────
  │ Allow Locdex to edit calculator.py?
  │
  │ [y] Allow once       [a] Allow similar this session
  │ [d] Show details     [n] Deny
  └──────────────────────────────────────────────────
  Choice ›
```

In interactive mode, llama.cpp model inference now runs in a **separate child process**, reused for the task. A model-load/decision call exceeding `LOCDEX_INFERENCE_TIMEOUT_SECONDS` (default **90 seconds**) terminates that child, raises a visible timeout, and rolls back Locdex-owned edits before returning to the input. Cancellation checks happen during model inference rather than waiting until the next agent step. Users on slower hardware can set the environment variable to a larger limit (20–600 seconds). The **12-step cap is separate**: a step cap by itself is not a wall-clock deadline. The isolated inference worker applies to interactive local runs; other execution paths may still require their own timeout policies. Long-running non-model tools and the operating system may have separate limits.

To change the inference timeout in PowerShell before running Locdex:

```powershell
$env:LOCDEX_INFERENCE_TIMEOUT_SECONDS = "120"
locdex
```


## Adaptive local inference budget and cloud recovery

Locdex computes independent model-load and generation timeouts for interactive local inference. Estimates use the selected GGUF model's approximate size, CPU core count, RAM pressure, backend/available GPU memory and requested output/context tokens. After successful inference calls, measured token throughput is saved **only in the local Locdex cache**, without prompts, source code, filenames, hardware IDs or user identifiers. The estimated generation budget adapts to these local observations; these are estimates, not performance guarantees.

Check the current estimate:

```powershell
locdex inference budget --model smoke
locdex inference budget --model qwen25-7b --max-tokens 512 --prompt-tokens 4000
locdex inference budget --model smoke --cloud-fallback
```

A configured cloud provider shortens the maximum estimated local inference wait (unless a user explicitly overrides it), but only when the selected sandbox permits cloud access. You can still set a fixed 20–600-second per-phase limit with `LOCDEX_INFERENCE_TIMEOUT_SECONDS`. Without the override, loading and generation have separate bounded deadlines. This is a **per-call** policy, distinct from the 12-step limit.

After a local native inference timeout, the execution wrapper converts the failure to a recorded agent outcome, relies on the hardened agent's rollback, and attempts its existing OpenAI-compatible cloud fallback **only if the user explicitly configured cloud inference**, enabled cloud usage, and allowed network access through the sandbox. Cancellation never causes escalation. Cloud fallback is not the same endpoint as Locdex's telemetry Worker; the telemetry API does not host models.

For PowerShell, configure the provider securely for the current session (never commit an API key):

```powershell
$env:LOCDEX_CLOUD_ENABLED = "1"
$env:LOCDEX_CLOUD_PROVIDER = "my-provider"
$env:LOCDEX_CLOUD_MODEL = "your-real-model-id"
$env:LOCDEX_CLOUD_BASE_URL = "https://your-provider.example/v1"
$env:LOCDEX_CLOUD_API_KEY = "your-api-key"
locdex cloud status
locdex
```

Inside the Locdex chat use `/sandbox workspace-network` before starting a task. The default `workspace-network` sandbox permits network-capable actions, subject to permission policies; cloud inference remains independently disabled until credentials and `LOCDEX_CLOUD_ENABLED=1` are configured. Select `workspace-write` for network-denied operation. To keep all work on-device, do not configure a cloud provider and leave the default sandbox unchanged.


## Built-in cloud providers

Use `locdex cloud providers` to list supported providers, API types, base URLs and expected **environment variable names**. No provider SDK is mandatory. Native Anthropic Messages uses forced JSON-schema tool use; OpenAI, Gemini, Groq, OpenRouter, DeepSeek, Together, Mistral, and custom services use compatible Chat Completions APIs. Support for an individual model depends on that provider's model-specific compatibility.

PowerShell, OpenAI example (replace with a **real** model available in your account):

```powershell
$env:LOCDEX_CLOUD_ENABLED = "1"
$env:LOCDEX_CLOUD_PROVIDER = "openai"
$env:LOCDEX_CLOUD_MODEL = "YOUR_OPENAI_MODEL_ID"
$key = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $key).Password
locdex cloud status
```

Anthropic example (choose a current supported Claude model ID):

```powershell
$env:LOCDEX_CLOUD_ENABLED = "1"
$env:LOCDEX_CLOUD_PROVIDER = "anthropic"
$env:LOCDEX_CLOUD_MODEL = "YOUR_CLAUDE_MODEL_ID"
$key = Read-Host "Anthropic API key" -AsSecureString
$env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new("", $key).Password
locdex cloud status
```

For Gemini, Groq, OpenRouter, DeepSeek, Together, and Mistral change the provider/model and set the respective `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `TOGETHER_API_KEY`, or `MISTRAL_API_KEY`. For any other OpenAI-compatible service set `LOCDEX_CLOUD_PROVIDER=custom`, `LOCDEX_CLOUD_BASE_URL`, `LOCDEX_CLOUD_MODEL`, and `LOCDEX_CLOUD_API_KEY`.

The existing `LOCDEX_CLOUD_API_KEY` environment variable overrides provider-specific key variables for backwards compatibility. Always remove the old variable before switching providers, or it may override the intended key. Environment variables apply to the current terminal session. Never commit keys or put them in a benchmark artifact.

Cloud inference still requires the user to opt into the `workspace-network` sandbox. The Cloudflare telemetry endpoint is **not** an inference provider.

## Public model qualification and benchmarks

Locdex now supports **sanitized qualification exports**, separate from a full benchmark suite:

```powershell
locdex model qualify smoke --max-steps 8
locdex benchmark export --input "PATH_FROM_REPORT_PATH_FIELD" --output "benchmarks/results/smoke-run-001.json"
locdex benchmark summary --dir benchmarks/results
```

These exports deliberately strip filenames, raw source, prompts, model text, private hardware identifiers, and full paths. Only publish results you have actually run and reviewed. Keep the original qualification JSON private (in the Locdex user cache). Qualification is a basic single-fixture probe, **not** LocdexBench, SWE-bench, or a statistically meaningful leaderboard. The source, benchmark definition, method, hardware tiers, model revisions, outcomes, and failure counts must accompany broader performance claims.

Publish vetted JSON in `benchmarks/results/` with Git, generate public summaries and charts in a future website `/benchmarks` page, and mirror reproducible datasets on Hugging Face. See `benchmarks/README.md`. No fake benchmark scores are included.


## Network-enabled default and local evidence-first cloud routing

New Locdex sessions and ordinary `locdex task` runs default to `workspace-network`. This is a capability policy, not permission to run arbitrary commands or transmit code: dangerous tools remain denied, the ordinary `ask` permission gate remains active, and cloud model execution requires explicit configuration and authorization. Existing saved sessions retain their prior sandbox selection; use `/sandbox workspace-network` in an existing session or `/sandbox workspace-write` to disable network access.

When local execution needs a configured cloud fallback, Locdex assembles a compact **evidence pack on the user's computer** before the first paid inference API request: targeted source snippets, retrieval plan, dependency graph, repository outline, local failure context, and bounded prior-session notes. Evidence collection uses a bounded budget based on the configured cloud context capacity and redacts detected secret patterns. The cloud agent skips redundant broad repository context and local pre-read copies while retaining the ability to reread exact files through tools. Cloud provider request messages can still contain task-relevant code, so cloud enablement constitutes consent to send that content to the selected provider; automatic redaction is not a guarantee against every secret.

## Bounded qualification

`locdex model qualify <model>` now runs **both** its prompt probe and the optional coding-agent probe through a reusable, isolated, killable local inference process. Each model load/generation call has an adaptive deadline. A timeout records a failed probe instead of freezing inside native llama.cpp; Ctrl+C records an `interrupted` report. Qualification is local-only, independent of the globally network-capable sandbox default, and does not silently route the test to cloud.


### Slow CPU calibration for local qualification

On low-memory, 1–2-physical-core CPU machines, a 35-second cold generation budget may stop a functioning model prematurely. Locdex now estimates more conservative **separate** load and generation deadlines for such machines and records locally observed timeout floors per model/backend/phase. The next automatic deadline can increase after a real timeout; explicit user overrides still take precedence. Native inference remains killable and maximum budgets remain bounded.

The model qualification probe uses a local model only; a timeout is reported as a failed probe, not a valid benchmark success. Previous exported qualification records remain separate and should not be overwritten when retrying.

```powershell
locdex inference budget --model smoke --max-tokens 32 --prompt-tokens 10
locdex model qualify smoke --prompt-only
```

For particularly slow hardware, users can choose an explicit per-phase ceiling for the current PowerShell session, e.g. `$env:LOCDEX_INFERENCE_TIMEOUT_SECONDS = "180"`. Increasing a deadline is not a substitute for measuring actual model completion quality.
