# Locdex — Architecture Overview

This document describes the current CLI-first Locdex architecture for contributors and testers. It replaces the older Ollama/mandatory-PR design.

---

## The core idea in one paragraph

Locdex runs as a command-line coding agent inside the repository the user launches it from. By default it uses a locally downloaded Qwen3-Coder GGUF through a hardware-aware embedded llama.cpp runtime; users may optionally install the smaller experimental Kimi-K3-distilled model instead. The local agent can inspect the repository, edit files directly, run commands and tests, and inspect Git state. Git mutations such as stage, commit, pull, and push are available only when the user's current request explicitly authorizes them. If the local model cannot complete the task, Locdex may use a cloud fallback, but only when the user has configured a provider and model. Telemetry is separate, off by default, and limited to privacy-minimized aggregate routing outcomes.

---

## System diagram

```text
User runs `locdex chat` inside a repository
                    │
                    ▼
          ┌──────────────────────┐
          │ Workspace + memory   │
          │ context              │
          └──────────┬───────────┘
                     ▼
          ┌──────────────────────┐
          │ Local agent          │
          │ Qwen default         │
          │ Kimi optional        │
          └──────────┬───────────┘
                     │
       ┌─────────────┼────────────────────┐
       ▼             ▼                    ▼
 read/search      edit files          run commands/tests
       │             │                    │
       └─────────────┼────────────────────┘
                     ▼
               working tree
                     │
         ┌───────────┴───────────┐
         │ local completes        │ local cannot complete
         ▼                        ▼
      response              configured cloud?
                                  │
                           ┌──────┴──────┐
                           │ no          │ yes
                           ▼             ▼
                       stop clearly   cloud model
                                         │
                                         ▼
                                validate candidate
                                before applying it

Explicit user Git request
("commit", "pull", "push", etc.)
                     │
                     ▼
            dedicated Git tools
```

The architecture is intentionally familiar to users of modern terminal coding agents: edits happen in the current working tree. Locdex's differentiation is the local-first runtime, routing, cost control, hardware-aware setup, safety boundaries, and transparent model/provider behavior—not a radically different editing workflow.

---

## Runtime and model layers

### Locdex process

`locdex` is a Python CLI installed through the package entry point. It runs on the developer's machine, not on a Locdex server.

### Local inference runtime

`runtime_manager.py` detects hardware and installs a matching **prebuilt** llama.cpp Python runtime. The first beta should prioritize a tested backend matrix rather than silently compiling native code on end-user machines.

Current backend selection logic includes:

- NVIDIA/CUDA when a supported CUDA wheel can be matched.
- Apple Silicon/Metal.
- Linux ROCm where available.
- Vulkan as a cross-vendor fallback on supported systems.
- CPU as the final fallback.

Hardware detection is cached but refreshed when the machine fingerprint changes.

### Model profiles

`model_profiles.py` defines the supported model choices.

| Key | Model | Status | Approx. download |
|---|---|---|---:|
| `qwen` | Qwen3-Coder 30B-A3B Instruct Q4_K_M | supported/default | ~18.6 GB |
| `kimi` | Qwen3.5 9B Kimi-K3 Distilled Q4_K_M | experimental | ~5.8 GB |

A user can install both. The selected model is persisted in Locdex settings and only one is normally loaded for a session.

Model files live in Locdex's cache, not inside the user's repository.

---

## Component map

| File | Responsibility |
|---|---|
| `main.py` | CLI entry point; `chat`, `setup`, model/runtime management, telemetry controls, startup diagnostics. |
| `config.py` | Persistent settings, cache/config directories, selected local model, inference settings and environment overrides. |
| `runtime_manager.py` | Hardware detection, backend selection, prebuilt runtime installation and runtime status. |
| `model_profiles.py` | Supported/default local-model definitions and hardware guidance. |
| `model_manager.py` | Model download, disk-space preflight, cache management and checksum verification where pinned. |
| `local_runtime.py` | Loads the GGUF through llama.cpp and provides structured completions; handles accelerated-load failure/CPU fallback. |
| `local_model.py` | Thin entry point from routing into the local agent. |
| `agent.py` | Multi-step agent loop. Chooses tools, receives results, edits the real workspace, and finishes or requests escalation. |
| `agent_tools.py` | Workspace-bounded tools: list/read/search/write/replace/delete, argv command execution, tests, Git status/diff/add/commit/pull/push. |
| `router.py` | Runs the local agent first; invokes cloud fallback only when local work is incomplete/escalated and the user configured cloud. |
| `cloud_fallback.py` | Loads the user's explicit provider/model configuration and calls only that provider/model chain. No default provider/model. |
| `validator.py` | Candidate validation for file sets, currently strongest for Python; uses a disposable staged copy on the host. Docker is not used in the current release. |
| `safety.py` | Path/code safety helpers used by the validation path. |
| `memory.py` | Project-local retrieval memory. Current implementation uses SQLite plus embeddings. |
| `telemetry.py` | Opt-in aggregate routing telemetry. No raw task/code/path/repo/device ID fields. |
| `editor.py` | Optional editor-context/diff helpers where retained. CLI remains the primary interface. |
| `planner.py` | Cost/usage reporting where enabled. |

---

## Agent interaction model

The agent operates directly in the current directory.

```text
> add input validation to the login endpoint

agent: list/search/read relevant files
agent: edit files in place
agent: run tests/checks
agent: inspect diff if useful
agent: final summary
```

Direct file edits are intentional. The user can always inspect/revert them with Git.

Git mutations have a stronger permission boundary:

```text
> commit these changes
> pull latest
> push this branch
```

Only a request containing the relevant intent should unlock the matching Git tool. The generic command runner blocks `git` and `gh` so the model cannot bypass that boundary by hiding Git actions inside an arbitrary shell command.

`ship it` may be supported as a convenience synonym for stage/commit/push, but Locdex does not depend on that phrase.

---

## Tool boundary

The local model does not receive unrestricted filesystem or shell access.

### File tools

The workspace resolver prevents traversal outside the repository and blocks direct access to internal/ignored directories such as `.git`, virtual environments, caches, and `node_modules`.

The model may:

- list files
- read files
- search code
- create/replace normal text files
- replace exact text
- delete files or empty directories

The model may not use those tools to reach paths outside the workspace.

### Command tool

`run_command` uses an argv list rather than shell text. This avoids shell interpolation by default. It applies a timeout, truncates output, and strips obvious secret-bearing environment variables before spawning the command.

Privilege-escalation/power commands and Git executables are blocked from this generic path.

### Git tools

Git operations use dedicated functions. Mutating operations are checked against the user's current request before the tool call is accepted.

---

## Tests and validation

There are two related but different paths.

### Normal local-agent workflow

The local agent can run the project's test suite directly in the current working tree. Current automatic test detection includes:

- Python: `pytest`
- TypeScript/JavaScript: `npm test`
- Go: `go test ./...`

This is intentionally similar to other terminal coding agents: the agent edits the working tree and then runs the project's own tooling.

### Isolated candidate validation

Cloud fallback returns candidate file payloads rather than receiving unrestricted tools. Before those candidates are applied, `validator.py` stages a disposable copy and validates there.

The current candidate validator is **Python-focused**. It performs syntax/security checks plus Ruff/tests in a disposable staged copy on the host. This protects the real working tree from ordinary validation mutations, but it is not a security sandbox. TypeScript/Go candidate validation should not be documented as production-ready until those paths are implemented and tested.

This distinction matters: Locdex can interact with many languages, but its deepest automatic validation is not yet equally mature across all of them.

---

## Routing

The current routing policy is deliberately simple for launch:

1. Run the selected local agent.
2. If it completes, stop.
3. If it explicitly escalates, hits the step limit, or the local runtime fails, consider cloud fallback.
4. Cloud fallback runs only if the user has explicitly configured a provider, model and credentials.
5. If cloud is not configured, report the local limitation clearly rather than silently selecting a service.

This is safer for the beta than pretending telemetry-derived routing thresholds are already proven.

Future releases may use aggregate outcome data to tune how many local attempts are worth making for particular `(language, task_category, local_model)` combinations. Those thresholds should be shipped as versioned Locdex policy, not fetched silently on every task.

---

## Cloud fallback

`cloud_fallback.py` intentionally has **no default provider and no default model**.

Examples of supported configuration patterns include:

- Anthropic direct API.
- OpenRouter when the user explicitly chooses OpenRouter.
- Other OpenAI-compatible endpoints through `custom` configuration.

OpenRouter-specific environment variables may remain in the OpenRouter provider adapter; that is not the same thing as making OpenRouter the default.

Telemetry must never override a user's pinned cloud provider/model. Aggregate provider success data may inform documentation or future recommendations, but the user's explicit configuration wins.

---

## Memory

Memory and telemetry are separate systems.

### Local memory

`memory.py` stores task/outcome information for the current user/project and uses it to provide relevant prior context. It does not need to leave the machine.

### Shared telemetry

Telemetry is not a shared-memory system and does not upload task text or solutions. It collects only coarse aggregate routing outcomes after explicit opt-in.

Do not blur these concepts in marketing: local memory can contain richer task-specific information because it stays local; telemetry must remain much more constrained because it may leave the machine.

---

## Telemetry contract

Telemetry is **off by default**.

The production-oriented design aggregates events locally before any network request. A bucket contains only fields like:

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

The schema deliberately excludes:

- raw task text
- source code or diffs
- file paths or filenames
- repository names or remote URLs
- Git usernames/emails
- device or installation identifiers
- hardware fingerprints
- exact per-task timestamps
- API keys or environment contents

The local client should expose:

```text
locdex telemetry status
locdex telemetry enable
locdex telemetry disable
locdex telemetry preview
locdex telemetry flush
locdex telemetry clear
```

`preview` must show exactly what would be uploaded.

If no official collector endpoint is configured, `flush` must not make a network request. Enabling telemetry may still aggregate the approved fields locally for testing.

A network server can inherently observe transport metadata such as an IP address even if it is absent from the JSON payload. The production collector/reverse proxy therefore needs an explicit no-retention/minimal-logging policy; the client alone cannot honestly promise that transport metadata never exists.

### How telemetry improves Locdex

Telemetry does not retrain Qwen or Kimi.

Its intended loop is:

```text
opted-in aggregate outcomes
        ↓
server-side aggregate analysis
        ↓
maintainer reviews sample size + confidence
        ↓
versioned routing-policy change
        ↓
normal Locdex release on PyPI
```

Use a minimum sample threshold before changing routing defaults. Do not let a handful of users cause automatic live policy changes.

---

## Package and update model

The public installation target is:

```bash
pip install locdex
locdex setup
```

The `pyproject.toml` console entry point creates the `locdex` command.

Package updates should be explicit:

```bash
python -m pip install --upgrade locdex
```

Model installation/removal/switching is also explicit through `locdex model ...` commands. Do not silently replace an 18.6 GB model during ordinary startup.

Runtime repair is explicit through `locdex runtime repair`.

This separation reduces surprise downloads and launch failures.

---

## CLI first

Locdex v0.1 is a command-line product.

A GUI or editor extension is deliberately deferred until the agent/runtime/install path is proven across real hardware. Editor tasks/keybindings may wrap the CLI without changing the core architecture.

---

## What Locdex does not do

- It does not require Ollama.
- It does not require a GUI.
- It does not choose a cloud provider/model for a user who has not configured one.
- It does not require a pull request for ordinary editing.
- It does not auto-commit or auto-push merely because it edited files.
- It does not upload code through telemetry.
- It does not use telemetry to fine-tune the local model.
- It does not silently download or replace large models during normal chat startup.
- It does not claim identical validation depth for every programming language.

---

## Contributor principle

When changing Locdex, keep the interaction familiar and move the product differentiation underneath it:

**familiar coding-agent workflow + local-first economics/privacy + explicit cloud choice + hardware-aware runtime + transparent routing + bounded tools + measurable reliability.**
