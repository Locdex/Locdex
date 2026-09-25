# Locdex — Full Build Specification

**One-line pitch:** A local-first terminal coding agent that edits your working tree like modern coding agents do, runs Qwen locally by default, escalates only to cloud models the user explicitly configured, and improves its routing policy from opt-in aggregate outcomes without uploading source code.

**What Locdex is:** a CLI coding agent with a familiar repository-editing workflow, a hardware-aware local runtime, explicit cloud choice, bounded tools, Git-intent controls, local memory, and a measurable routing layer.

**What Locdex is not:** a new foundation model, a GUI-first IDE, an Ollama wrapper, a mandatory-PR workflow, or a system that silently picks a cloud vendor for the user.

This document is the source of truth for the current v0.1/beta direction. Older Ollama-specific and “never touch the working tree until `ship it`” designs are superseded by this version.

---

## 1. System Overview

```text
┌──────────────────────────────────────────────────────────┐
│                  LOCAL — developer machine               │
│                                                          │
│  user task                                               │
│     │                                                    │
│     ▼                                                    │
│  workspace context + local memory                        │
│     │                                                    │
│     ▼                                                    │
│  local agent                                             │
│  Qwen3-Coder default / Kimi optional                     │
│     │                                                    │
│     ├── read/search files                                │
│     ├── edit files directly                              │
│     ├── run commands/tests                               │
│     ├── inspect Git status/diff                          │
│     └── explicit Git actions when user asks              │
│                                                          │
│     └──── if local cannot complete ──────┐               │
└───────────────────────────────────────────┼───────────────┘
                                            ▼
                              user-configured cloud only
                                            │
                                            ▼
                                   candidate validation
                                            │
                                            ▼
                                        workspace
```

### Core design decisions

| Decision | Reasoning |
|---|---|
| CLI first | The repository, shell and Git already live in the terminal. This keeps v0.1 focused on agent quality and install reliability rather than UI work. |
| Python package | Gives a straightforward `pip install locdex` distribution path and an ordinary console-script entry point. |
| Embedded llama.cpp runtime | Locdex owns the user experience instead of requiring Ollama or another consumer model application. |
| Qwen3-Coder default | More established coding baseline for launch; strong repository/tool-use fit. |
| Kimi distill optional | Smaller download and lower RAM requirement, but still experimental until Locdex-specific benchmarks are strong enough. |
| Direct working-tree edits | Matches Codex/Claude-Code-style expectations. Users can inspect/revert with Git. |
| Explicit Git intent | Editing code is not permission to stage, commit, pull or push. Dedicated Git tools enforce this boundary. |
| No default cloud provider | The user's provider/model choice is authoritative. Cloud is disabled when unconfigured. |
| Aggregate telemetry only | Routing outcomes are useful; raw tasks/code are unnecessary and too sensitive. |
| Release-time routing policy | Telemetry may inform future defaults, but should not silently change cloud providers or live routing from a backend response. |

---

## 1.1 How people actually use Locdex

The normal session is intentionally unsurprising:

```bash
cd my-project
locdex chat
```

```text
> inspect this repo and explain the login flow

> fix the empty-token bug and add a test

> run the tests

> show me the diff

> commit this with message "Fix empty-token login handling"

> push this branch
```

The agent can edit files during the coding turns. `commit`, `pull`, and `push` require explicit user intent in the current request.

`ship it` can remain as a convenience phrase, but it is not a required state transition. It may authorize stage/commit/push when the command semantics are clear.

### CLI surface for v0.1

```text
locdex chat
locdex setup
locdex model list|install|status|remove|use
locdex runtime status|install|repair
locdex telemetry status|enable|disable|preview|flush|clear
```

One-shot task support may remain:

```bash
locdex --task "fix the failing parser test"
```

Editor wrappers can call the CLI later, but no GUI is required for v0.1.

---

## 1.2 Language support

Be precise about two different capabilities.

### Agent interaction

The file/search/edit tools can work with ordinary UTF-8 text across many languages. The model can reason about languages beyond the deeply validated set.

### Automatic host test detection

Current automatic test detection in `agent_tools.py` includes:

| Ecosystem | Marker | Command |
|---|---|---|
| Python | `pytest.ini` or `pyproject.toml` | `python -m pytest -q` |
| TypeScript/JavaScript | `package.json` | `npm test -- --runInBand` |
| Go | `go.mod` | `go test ./...` |

### Isolated candidate validation

The current staged-copy validator is Python-focused and does not use Docker. It should not be marketed as equally complete for TypeScript/JavaScript or Go until those paths are implemented and tested.

This is an intentional honesty rule: “the agent can edit this language” and “Locdex has deep automatic validation for this language” are separate claims.

---

## 1.3 Local models

Locdex ships model **profiles**, not model weights inside the Python wheel.

### Supported default

```text
Key: qwen
Model: Qwen3-Coder 30B-A3B Instruct
Quant: Q4_K_M
Approximate download: 18.6 GB
Minimum launch RAM target: ~24 GB
Recommended RAM: 32 GB
Status: supported/default
```

### Optional experimental model

```text
Key: kimi
Model: Qwen3.5 9B Kimi-K3 Distilled
Quant: Q4_K_M
Approximate download: 5.8 GB
Minimum launch RAM target: ~12 GB
Recommended RAM: 16 GB
Status: experimental
```

A machine may have both models downloaded. `locdex model use ...` changes which one is selected without forcing a redownload.

Do not make a community model the only supported launch path until it has passed the Locdex agent benchmark and hardware matrix.

---

## 1.4 Cloud fallback

Cloud fallback is an optional escalation tier, not the default product.

Rules:

1. No provider configured → no cloud call.
2. No model configured → no cloud call.
3. User-pinned provider/model wins over telemetry or heuristics.
4. OpenRouter is one selectable provider, not a default.
5. Custom OpenAI-compatible endpoints are allowed when explicitly configured.
6. Cloud output is never used to fine-tune Qwen/Kimi through this system.

Examples:

```bash
# Anthropic
export LOCDEX_CLOUD_PROVIDER=anthropic
export LOCDEX_CLOUD_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=...

# OpenRouter — only if selected
export LOCDEX_CLOUD_PROVIDER=openrouter
export LOCDEX_CLOUD_MODEL=provider/model
export OPENROUTER_API_KEY=...

# Generic OpenAI-compatible endpoint
export LOCDEX_CLOUD_PROVIDER=custom
export LOCDEX_CLOUD_MODEL=my-model
export LOCDEX_CLOUD_BASE_URL=https://provider.example/v1/chat/completions
export LOCDEX_CLOUD_API_KEY=...
```

---

## 2. Repository Layout

A current production-oriented source tree should look approximately like:

```text
Locdex/
├── pyproject.toml
├── README.md
├── SETUP_GUIDE.md
├── ARCHITECTURE.md
├── BUILD_SPEC.md
├── src/
│   └── locdex/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── runtime_manager.py
│       ├── model_profiles.py
│       ├── model_manager.py
│       ├── local_runtime.py
│       ├── local_model.py
│       ├── agent.py
│       ├── agent_tools.py
│       ├── router.py
│       ├── cloud_fallback.py
│       ├── memory.py
│       ├── telemetry.py
│       ├── safety.py
│       ├── validator.py
│       ├── parser.py
│       ├── editor.py          # optional/editor bridge
│       ├── planner.py         # metrics/cost reporting
└── tests/
```

Do not commit `__pycache__/`, `.pytest_cache/`, virtual environments, GGUF models, or local telemetry cache files.

---

## 3. Component-by-Component Technical Specification

### 3.1 `runtime_manager.py` — hardware detection and binary runtime installation

The installer must minimize first-run failure modes.

`locdex setup` should:

1. Detect operating system and architecture.
2. Detect system RAM.
3. Prefer a specific accelerator backend when available.
4. Choose a known prebuilt wheel source.
5. Install with `--only-binary=:all:` so pip does not silently fall back to a native compiler toolchain.
6. Persist a runtime marker containing backend/fingerprint/version.
7. Re-detect after hardware/driver changes.

Backends currently considered:

- CUDA
- Metal
- ROCm
- HIP Radeon where explicitly enabled
- Vulkan
- CPU

If the selected accelerated runtime cannot load the model, Locdex may retry on CPU once and explain the fallback.

For beta reliability, officially qualify Python 3.10–3.12 first. Expand only after real hardware tests confirm wheels and inference for additional versions.

---

### 3.2 `model_profiles.py` and `model_manager.py`

`model_profiles.py` is the release policy for supported models.

Each profile should include:

- stable key (`qwen`, `kimi`)
- display name
- Hugging Face repository
- filename pattern
- expected checksum when pinned
- approximate size
- minimum/recommended RAM
- support status
- concise description

`model_manager.py` should:

- perform disk-space preflight
- download into the Locdex cache, not the repo
- verify the checksum when one is pinned
- persist enough metadata to report status
- support remove/list/status without importing the runtime

Do not silently update or replace an installed 18+ GB model during ordinary chat startup.

---

### 3.3 `local_runtime.py`

Responsibilities:

- load the selected GGUF with llama.cpp
- use hardware-aware GPU-layer defaults
- expose structured/JSON completion
- control context size, token budget and temperature
- provide a small inference smoke test
- fail with actionable errors

The smoke test is part of setup because a successful download is not proof that the model can load and generate on that machine.

---

### 3.4 `agent.py` — multi-step local agent loop

The agent receives:

- system instructions
- workspace context
- user task
- tool descriptions
- prior tool results

It repeatedly returns one of:

```json
{"action": "tool", "tool": "read_file", "args": {"path": "..."}}
```

```json
{"action": "final", "summary": "...", "confidence": 0.87}
```

```json
{"action": "escalate", "reason": "...", "confidence": 0.2}
```

The tool loop is bounded by `max_agent_steps`.

Important operating rules:

- inspect before editing
- edit the real working tree when the task requires it
- run relevant checks after edits
- keep changes scoped
- never access paths outside the workspace
- never use mutating Git tools without matching user intent
- escalate only when needed

---

### 3.5 `agent_tools.py` — bounded workspace tools

#### File boundary

All file paths are resolved under the workspace root. Path traversal and internal/ignored directories are blocked.

#### Read/search tools

- `list_files`
- `read_file`
- `search_code`

#### Mutation tools

- `write_file`
- `replace_in_file`
- `delete_path`

Edits are immediate in the current working tree.

#### Commands

`run_command` accepts argv arrays rather than arbitrary shell strings. It applies timeouts and strips secret-looking environment variables.

Block at minimum:

- privilege escalation
- shutdown/reboot commands
- `git` and `gh` through the generic runner

The last rule is important: Git must go through dedicated tools so the explicit-intent guard cannot be bypassed.

#### Tests

`run_tests` detects Python, JS/TS and Go test runners from project markers.

#### Git

- `git_status`
- `git_diff`
- `git_add`
- `git_commit`
- `git_pull`
- `git_push`

Mutating operations require explicit user intent in the current task.

---

### 3.6 `router.py`

Launch behavior should remain simple until the telemetry dataset is real.

```text
run selected local agent
        │
        ├── completed → return local result
        │
        └── incomplete/escalate/runtime failure
                     │
                     ▼
            cloud configured?
              │             │
             no            yes
              │             │
          stop clearly   run user's cloud model(s)
```

The router should return metadata useful for local logs/telemetry:

```python
{
    "source": "local" | "cloud" | "none",
    "provider": None | "anthropic" | "openrouter" | "custom",
    "model": None | "...",
    "escalation_reason": None | "local_runtime_failure" | "local_incomplete" | ...,
    "result": {...},
}
```

Do not claim category-threshold routing is active until it is actually backed by enough data and tested policy.

---

### 3.7 `cloud_fallback.py`

`cloud_fallback.py` must never infer an unconfigured provider.

Configuration order:

1. environment overrides
2. saved Locdex settings
3. provider adapter defaults only for endpoint/key-variable names **after** a provider is selected

For example, it is fine for the OpenRouter adapter to know that OpenRouter usually reads `OPENROUTER_API_KEY`; that does not make OpenRouter the default.

Cloud request adapters may differ by provider. Keep the provider/model selection separate from request-shape code.

Telemetry must not override the provider/model a user selected.

---

### 3.8 `validator.py` and `safety.py`

The isolated validator is for candidate payloads where Locdex wants a stronger gate before applying them.

Correct sequence:

```text
real workspace
      │
      └── copy → disposable staged workspace
                         │
                  apply candidate files
                         │
             syntax/static safety checks
                         │
                  staged host validation
                  network disabled
                         │
                  lint + tests
```

Never mount the real repository read-write into the validation container.

Current isolated candidate validation is Python-focused. Extend language support only with matching tests and explicit documentation.

---

### 3.9 `memory.py`

Memory is local and separate from telemetry.

Current design:

- SQLite store
- task/outcome entries
- embedding-based retrieval
- similar prior outcomes inserted into future context

The default memory implementation uses lightweight local text similarity and does not download or require a separate embedding model. The `embedding` database column is retained only for backward compatibility with older local databases.

No project memory should be uploaded by telemetry.

---

### 3.10 `telemetry.py` — privacy-minimized shared routing outcomes

#### Goal

Answer questions like:

- Does Qwen succeed locally often enough for this task category?
- Is Kimi good enough on 16 GB-class machines to move out of experimental status?
- Which languages/categories cause frequent cloud escalation?
- Is a routing-policy change supported by enough real outcomes?

Telemetry should **not** answer “what code did this user write?”

#### Off by default

```text
telemetry_enabled = false
```

Users control it explicitly:

```bash
locdex telemetry enable
locdex telemetry disable
```

An environment override may exist for automated testing, but it should not be the only consent mechanism.

#### Local classification only

The raw user task is classified locally into a fixed category such as:

```text
bug_fix
feature
refactor
tests
documentation
dependency
configuration
git_operation
code_review
other
```

Only the category label enters telemetry. The original task string does not.

#### Aggregate before sending

Do not write an event-by-event cloud log with exact timestamps.

Locdex should aggregate locally into buckets such as:

```json
{
  "period": "2026-09",
  "task_category": "bug_fix",
  "language": "python",
  "route": "local",
  "local_model": "qwen",
  "cloud_provider": null,
  "cloud_model": null,
  "escalation_reason": "none",
  "runs": 12,
  "successes": 10,
  "total_attempts": 15
}
```

The client payload should contain no unique user/install/device/repo identifier.

#### Fields that must never exist in the outbound schema

- source code
- diffs
- raw prompt/task text
- file/folder paths
- repository name or remote URL
- Git username/email
- branch names
- environment-variable values
- API keys
- machine fingerprint
- exact timestamps
- local memory entries

This is stronger than redaction: the telemetry API should not accept these fields at all.

#### Preview before send

```bash
locdex telemetry preview
```

must show the exact payload shape currently queued.

#### No endpoint means no network

The development build should use an empty default telemetry endpoint until an official collector exists.

```text
LOCDEX_TELEMETRY_ENDPOINT unset
→ flush returns no_endpoint
→ no HTTP request occurs
```

This lets the schema/client be tested before a privacy policy or backend is prematurely deployed.

#### Collector requirements

The future collector should:

- accept only the schema version/known fields
- reject unexpected free-text fields
- aggregate quickly
- avoid persistent per-IP logs where operationally possible
- have a documented retention window
- never enrich events with identity data
- expose no per-user analytics product

Even with no IP in the JSON, network infrastructure can observe source IPs. Do not call the system perfectly anonymous unless the server/proxy configuration justifies that claim. “Privacy-minimized aggregate telemetry” is more accurate.

#### How telemetry changes Locdex

Telemetry should feed a release process, not live arbitrary backend control:

```text
aggregate data
  ↓
minimum sample-size gate
  ↓
maintainer analysis
  ↓
versioned routing thresholds/model status
  ↓
Locdex release
  ↓
pip install --upgrade locdex
```

A minimum sample size (e.g. 50+ outcomes for a specific dimension before changing a default) prevents sparse/noisy data from setting policy.

Telemetry may also help decide whether Kimi should be promoted from experimental, but that decision must combine aggregate use with Locdex's controlled benchmark suite.

---

### 3.11 `main.py` — CLI and setup UX

Primary commands:

```text
locdex chat
locdex setup
locdex model ...
locdex runtime ...
locdex telemetry ...
```

`locdex setup` should:

1. detect hardware
2. install a prebuilt runtime
3. ask/select model
4. check RAM/disk
5. download model
6. verify checksum when available
7. run inference smoke test
8. report the selected model/backend

Do not download models during `pip install locdex`.

Do not prompt for telemetry before there is a real collector/consent story ready. The command can exist in advance; shared sending remains off.

---

## 4. Prompting and Agent Protocol

Prompts should reinforce tool use rather than produce giant code blobs.

Core behavior:

- inspect relevant files before editing
- use tools to apply changes
- run tests/checks where available
- be explicit when something was not tested
- do not claim Git actions occurred unless the dedicated tool succeeded
- do not leak secrets from environment or ignored directories
- escalate when local execution genuinely cannot complete

Keep the structured agent protocol stable enough to test across Qwen and Kimi.

---

## 5. Installation and Packaging

### User install

Public target:

```bash
python -m pip install locdex
locdex setup
```

A standalone CLI installation may also use `pipx`.

The wheel should remain relatively small. The 18.6 GB Qwen model is downloaded only by `locdex setup`/`locdex model install qwen`.

### Development install

```bash
git clone https://github.com/bandojayy/Locdex.git
cd Locdex
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
python -m pip install -e .
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### `pyproject.toml`

Minimum shape:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "locdex"
version = "0.1.0b1"
description = "Local-first agentic coding CLI with hardware-aware local inference and explicit cloud fallback."
requires-python = ">=3.10,<3.13"

[project.scripts]
locdex = "locdex.main:cli"

[tool.setuptools.packages.find]
where = ["src"]
```

Use a beta/pre-release version for the first public hardware test rather than presenting the first field build as 1.0.

### Dependency discipline

The base install should contain only dependencies required for ordinary CLI use.

Review heavy dependencies before public beta. In particular:

- `llama-cpp-python` should be installed by the hardware-aware setup step, not as an unconditional build dependency.
- Docker is out of scope for the current release. Stronger container isolation MAY be introduced later as an optional hardening layer.
- `pytest`/`ruff` belong to development or validation paths, not necessarily every end-user install.
- The base install MUST NOT pull a secondary embedding model. Semantic-memory upgrades MAY be introduced later as optional extras.

Reducing dependency surface directly reduces installation failures.

---

## 6. Hardware Targets

| Use case | Minimum target | Comfortable target | Notes |
|---|---:|---:|---|
| Locdex CLI development | 8 GB RAM | 16 GB | Without running Qwen locally |
| Kimi experimental local model | ~12 GB RAM | 16 GB | ~5.8 GB model |
| Qwen default local model | ~24 GB RAM | 32 GB | ~18.6 GB model; context length matters |
| Qwen with strong GPU offload | depends on backend/VRAM | 24 GB-class VRAM ideal | Exact behavior must be measured per backend |
| Storage for Qwen setup | ~30 GB free | 40+ GB | Includes model + cache headroom |
| Storage for Kimi setup | ~12 GB free | 20 GB | Includes model + cache headroom |

Do not market an environment as supported until the full setup/inference/agent sequence has passed on real hardware.

---

## 7. Build and Test Order

### Phase 1 — deterministic local functionality

- CLI entry point
- workspace tools
- Git-intent guard
- local agent loop
- Qwen model profile
- runtime hardware detection
- model download/checksum
- smoke test

### Phase 2 — optional paths

- Kimi experimental profile
- user-configured cloud fallback
- isolated cloud candidate validation
- telemetry client/schema

### Phase 3 — public beta hardening

Test at minimum:

- Windows 11 native
- Ubuntu/Linux
- macOS Apple Silicon
- CPU-only
- NVIDIA CUDA
- Apple Metal
- at least one AMD/Vulkan or ROCm path before claiming AMD support

For each supported environment test:

```text
install
→ locdex setup
→ hardware detection
→ prebuilt runtime install
→ Qwen download
→ checksum
→ model load
→ structured smoke response
→ repo inspect
→ file edit
→ tests
→ diff
→ explicit commit
→ explicit push (disposable remote)
→ cloud-disabled failure case
→ upgrade/uninstall
```

Kimi should run through the same sequence before its status changes from experimental.

---

## 8. Telemetry Consent Text

Use concrete language rather than “anonymous analytics”. Example:

```text
Locdex can optionally share privacy-minimized aggregate routing outcomes to
help improve future routing defaults.

If enabled, Locdex may send aggregate buckets containing only:
- task category from a fixed list
- programming-language bucket
- local model key (for example qwen/kimi)
- local vs cloud route
- configured cloud provider/model label when cloud was used
- success/failure counts
- total local attempts
- coarse month bucket
- fixed escalation-reason label

Locdex telemetry does NOT send your source code, diffs, raw task text, file
paths, repository name/URL, Git identity, API keys, local memory, hardware
fingerprint, or an installation/user identifier.

Telemetry is off by default. Run `locdex telemetry preview` at any time to see
exactly what is queued.

Enable telemetry? [y/N]
```

Do not show this prompt until an official telemetry collector and retention policy are ready. Before that, keep the feature disabled by default and expose the preview/client for development testing only.

---

## 9. What “learning” means

Keep three concepts separate.

| Layer | What changes | What does not change |
|---|---|---|
| Local memory | Prompt context becomes more relevant for this user/project | Qwen/Kimi weights do not change |
| Shared telemetry | Maintainer can tune routing defaults/model status in later releases | No user code is redistributed; cloud choice is not overridden live |
| Future fine-tuning | Model weights could change | Not part of v0.1 and not implied by telemetry |

Locdex's credible wedge is better model/routing decisions and workflow economics—not claiming aggregate metadata makes an open model magically become a frontier model.

---

## 10. Release Pipeline

### Build

```bash
python -m pip install --upgrade build twine
python -m build
```

Expected output:

```text
dist/
  locdex-<version>-py3-none-any.whl
  locdex-<version>.tar.gz
```

### Test release

Use TestPyPI or a private test index before the public release.

Validate in a fresh environment, not the developer's existing venv.

### Publish

Publish only after:

- unit tests pass
- clean package install passes
- `locdex --help` works
- `locdex setup` works on at least the initial supported OS/hardware matrix
- Qwen smoke inference passes
- the disposable-repository agent test passes

### Update path

Users update the CLI explicitly:

```bash
python -m pip install --upgrade locdex
```

Model/runtime changes remain explicit through Locdex commands. Avoid surprise multi-gigabyte downloads during package update.

---

## 11. Reliability and Privacy Gates Before Beta

Before a public beta, verify all of the following:

- no Ollama dependency remains in normal setup/runtime code or docs
- no default cloud provider/model is silently selected
- Qwen is the supported default and Kimi is clearly experimental
- runtime installation uses binary wheels only
- unsupported backend failures are actionable
- model download has disk preflight
- Qwen checksum verification works
- local file tools cannot escape workspace
- generic command runner cannot execute Git to bypass intent checks
- telemetry is off by default
- telemetry preview contains no raw text/path/repo/device identity
- clean package contains every imported module (`telemetry.py`, `editor.py`, `planner.py`, etc.)
- no `__pycache__`/`.pytest_cache` is included in the release artifact
- package install is tested from the built wheel, not only `pip install -e .`

---

## 12. Differentiation Summary

Do not pitch Locdex as merely “another local coding agent”. That category already exists.

The stronger position is:

1. **Familiar terminal-agent workflow** — inspect, edit, test, diff, Git.
2. **Local-first default** — Qwen runs on the user's machine after one explicit model download.
3. **Hardware-aware installation** — Locdex chooses a tested runtime instead of asking users to become inference-stack experts.
4. **Explicit cloud choice** — no hidden default vendor/model.
5. **Cost control** — routine work stays local; cloud is escalation rather than the baseline.
6. **Bounded tools and Git intent controls** — freedom to edit without silently committing/pushing.
7. **Transparent model options** — Qwen supported, Kimi experimental, status can change only after evidence.
8. **Privacy-minimized telemetry** — aggregate outcomes can improve future routing policy without collecting code.
9. **Measured reliability** — supported hardware means tested hardware, not theoretical compatibility.

That is the build direction to preserve as the codebase evolves.
