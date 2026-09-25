# Locdex Setup Guide

This guide describes the current CLI-first Locdex architecture. It replaces the older Ollama-based setup flow.

Locdex is a local-first coding agent that runs inside the repository you launch it from. It can inspect files, edit the working tree directly, run commands/tests, inspect Git state, and perform Git operations when the user explicitly asks. The default local model is Qwen3-Coder; the smaller Kimi-K3-derived model is optional and experimental.

---

## 1. What gets installed

A normal user installation has three layers:

1. **Locdex CLI** — installed as a Python package.
2. **Local inference runtime** — a hardware-matched prebuilt `llama-cpp-python` runtime installed by `locdex setup`.
3. **Local model** — downloaded by Locdex into its own cache after the user chooses Qwen or Kimi.

There is **no Ollama requirement** and no separate model-server UI. Hugging Face is used only as a model distribution source; inference happens on the user's machine.

The normal public flow is:

```bash
pip install locdex
locdex setup
cd path/to/my-project
locdex chat
```

For a standalone CLI installation, `pipx install locdex` is also appropriate once the package is published.

> During development, before the PyPI release exists, clone the repository and use `python -m pip install -e .` instead of `pip install locdex`.

---

## 2. Supported launch environment

For the first beta, qualify a deliberately small test matrix instead of claiming every environment works.

### Required

- Python **3.10, 3.11, or 3.12** for the initial beta test matrix.
- Git on `PATH`.
- Enough free disk and RAM for the selected model.
- Internet access during first setup/model download.

### Operating systems

Locdex is intended to run natively on:

- Windows 10/11
- macOS, including Apple Silicon
- Linux

WSL is not required by the current architecture.

### Docker

Docker is **not required or used in the current release**. Candidate validation runs in a disposable copy of the repository on the host with shell invocation disabled and a reduced environment. Stronger container isolation may be added later as an optional hardening layer.

---

## 3. Hardware and model choice

Locdex detects the machine during setup and selects an appropriate local inference backend where a tested prebuilt runtime is available.

| Model | Status | Download | Minimum RAM target | Recommended RAM | Use case |
|---|---|---:|---:|---:|---|
| Qwen3-Coder 30B-A3B Q4_K_M | Supported / default | ~18.6 GB | ~24 GB | 32 GB | Main release model; stronger coding baseline |
| Qwen3.5 9B Kimi-K3 Distilled Q4_K_M | Experimental | ~5.8 GB | ~12 GB | 16 GB | Smaller optional model for lighter machines/testing |

These RAM figures are conservative Locdex launch targets, not guarantees for every context size or backend. Context length, GPU offload, open applications, and operating-system overhead change actual memory use.

For a Qwen installation, keep **at least ~30 GB free disk** during setup. For Kimi, keep **at least ~12 GB free disk**. The extra space gives the downloader and cache room to work safely.

---

## 4. Install Locdex

### Public package

Once published to PyPI:

```bash
python -m pip install --upgrade pip
python -m pip install locdex
```

Check the command:

```bash
locdex --help
```

The `locdex` command is created by the package's `[project.scripts]` entry point.

### Contributor/development install

```bash
git clone https://github.com/bandojayy/Locdex.git
cd Locdex
python -m venv .venv
```

Activate the environment.

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

---

## 5. Run first-time setup

```bash
locdex setup
```

Setup should perform these operations in order:

1. Detect OS, architecture, RAM, and available accelerator.
2. Select a supported inference backend such as CUDA, Metal, ROCm/Vulkan, or CPU.
3. Install a **prebuilt** runtime wheel. Locdex should not silently compile llama.cpp on an end user's machine.
4. Ask which local model to use, defaulting to Qwen.
5. Check available RAM and disk before downloading.
6. Download the selected GGUF into Locdex's cache.
7. Verify the model checksum where Locdex has a pinned checksum.
8. Load the model with a small context and run an inference smoke test.
9. Report success only after the runtime and model actually produce a valid response.

Explicit model selection is also supported:

```bash
locdex setup --model qwen
locdex setup --model kimi
```

To inspect the detected backend without downloading a model:

```bash
locdex runtime status
```

To repair/reinstall the runtime after a driver or hardware change:

```bash
locdex runtime repair
```

---

## 6. Model management

List available model profiles:

```bash
locdex model list
```

Install one without changing the other:

```bash
locdex model install qwen
locdex model install kimi
```

Switch the selected model without redownloading:

```bash
locdex model use qwen
locdex model use kimi
```

Inspect model status:

```bash
locdex model status
```

Remove a local model:

```bash
locdex model remove kimi
```

Both models may be downloaded at the same time. Only the selected model should be loaded for a normal session.

---

## 7. Start Locdex in a repository

Change into the project you want Locdex to work on:

```bash
cd path/to/project
locdex chat
```

That directory becomes the workspace boundary.

Typical interaction:

```text
> inspect this repository and explain the authentication flow

> fix the failing login test

> run the tests

> show me the diff

> commit these changes with message "Fix empty-token login handling"

> push this branch
```

Locdex is allowed to edit normal files in the working tree immediately, like other terminal coding agents. It should not require a special `ship it` ceremony before every edit.

Git mutations are different: `git add`, `commit`, `pull`, and `push` are exposed through dedicated tools and should only run when the user's current request explicitly authorizes the relevant Git action. `ship it` may remain a convenience phrase, but it is not the architecture.

---

## 8. Cloud fallback is optional

Locdex has **no default cloud provider and no default cloud model**. If the user configures nothing, cloud fallback is disabled.

The selected cloud provider/model must come from the user's configuration.

### Anthropic example

```bash
export LOCDEX_CLOUD_PROVIDER=anthropic
export LOCDEX_CLOUD_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=your_key
```

### OpenRouter example

OpenRouter remains a supported option, but only when explicitly selected:

```bash
export LOCDEX_CLOUD_PROVIDER=openrouter
export LOCDEX_CLOUD_MODEL=your/chosen-model
export OPENROUTER_API_KEY=your_key
```

### Other OpenAI-compatible provider

```bash
export LOCDEX_CLOUD_PROVIDER=custom
export LOCDEX_CLOUD_MODEL=provider-model-id
export LOCDEX_CLOUD_BASE_URL=https://provider.example/v1/chat/completions
export LOCDEX_CLOUD_API_KEY=your_key
```

Never commit API keys to the repository. Environment variables, an OS secret store, or a dedicated secrets manager are preferable.

---

## 9. Telemetry / shared routing learning

Telemetry is **off by default**.

The current design records only coarse aggregate routing outcomes after the user opts in. It does not accept source code, raw task text, file paths, repository names, machine identifiers, or exact task timestamps.

Useful commands:

```bash
locdex telemetry status
locdex telemetry enable
locdex telemetry disable
locdex telemetry preview
locdex telemetry flush
locdex telemetry clear
```

`preview` is important: it shows exactly what would be uploaded.

The test build does not need to ship with a live collector URL. If no telemetry endpoint is configured, enabling telemetry only aggregates the approved fields locally; nothing leaves the machine. Do not add a production endpoint until the collector, retention policy, and privacy configuration are ready.

See `ARCHITECTURE.md` and `BUILD_SPEC.md` for the full telemetry contract.

---

## 10. Where Locdex stores things

Locdex should keep its own caches/config outside the user's repository through `platformdirs`.

Typical categories are:

- Config: selected model, telemetry opt-in, cloud settings that are safe to store.
- Cache: model files, runtime profile, telemetry aggregates.
- Project: only the user's project files and project-local memory database if that feature remains project-scoped.

`__pycache__/`, `.pytest_cache/`, virtual environments, model caches, and telemetry cache files should never be committed to the user's project.

---

## 11. Testing a new installation

After setup:

```bash
locdex runtime status
locdex model status
```

Then use a disposable Git repository for the first behavioral test:

```bash
mkdir locdex-smoke-test
cd locdex-smoke-test
git init
```

Create a tiny project and test these behaviors:

- repository inspection
- file creation/editing
- test execution
- failed-test recovery
- `git status` and diff inspection
- commit only after explicit instruction
- push only after explicit instruction
- local-model failure with cloud fallback disabled
- cloud fallback with the user's configured provider
- telemetry off by default

Do not use an important repository for the first hardware/runtime test.

---

## 12. Troubleshooting

| Problem | What to check |
|---|---|
| `locdex: command not found` | Confirm Locdex was installed into the active Python environment and that its scripts directory is on `PATH`. |
| Runtime installation fails | Run `locdex runtime status`; confirm Python version and detected backend. The installer intentionally refuses source compilation when a tested binary wheel is unavailable. |
| Qwen download fails | Check free disk, network connection, and Hugging Face availability; retry `locdex model install qwen`. |
| Model downloads but will not load | Check system RAM/VRAM and lower `LOCDEX_N_CTX`; run `locdex runtime repair` after driver changes. |
| NVIDIA GPU is ignored | Confirm `nvidia-smi` works in the same terminal. |
| Apple Silicon uses CPU | Run `locdex runtime status` and confirm the Metal backend was selected. |
| Kimi behaves inconsistently | It is experimental; switch back with `locdex model use qwen`. |
| Cloud fallback does nothing | This is expected unless provider, model, endpoint (when needed), and API key are explicitly configured. |
| Staged validation tool is unavailable | Install development tools with `python -m pip install -e ".[dev]"` and ensure the project's own test dependencies are installed. |
| Agent changed a file you did not want | Use Git/diff to inspect/revert. Direct workspace editing is intentional; Git commit/push still requires explicit instruction. |

---

## 13. Beta release rule

Do not call an environment “supported” merely because the code should work there. Add it to the supported matrix only after the full sequence succeeds on real hardware:

```text
install → hardware detect → runtime install → model download → checksum → load → smoke test
→ repository inspect → edit → tests → Git intent checks → clean uninstall/upgrade
```

That is the standard to use for the first public Locdex release.
