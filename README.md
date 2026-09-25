# Locdex: Local-First Agentic Coding CLI

Locdex is a local-first coding agent that works directly in the developer's current directory. It can inspect a repository, edit files, run commands and tests, inspect diffs, and perform Git operations when the user explicitly asks. Its differentiators are local-first execution, model routing, cost control, bounded tools, validation, and transparent agent behavior.

## v1.3 launch runtime

Locdex no longer requires Ollama and no longer makes `pip install locdex` compile llama.cpp on the user's machine.

`locdex setup` now:

1. detects the operating system, CPU architecture, system RAM, and available accelerator;
2. chooses a prebuilt llama-cpp-python runtime for CPU, Apple Metal, NVIDIA CUDA, Linux ROCm, Windows HIP Radeon, or Vulkan where detected;
3. caches the detected hardware fingerprint and re-detects if the machine changes;
4. lets the user choose Qwen3-Coder or the optional Kimi-distilled model;
5. checks available disk space before downloading;
6. verifies the pinned Qwen model SHA-256;
7. runs a small-context local inference smoke test before declaring setup complete.

If automatic GPU model loading fails, Locdex retries once on CPU rather than immediately failing the whole session.

## Local model choices

### Qwen3-Coder — supported default

- Base: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- Locdex GGUF: `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF`
- Quant: Q4_K_M
- Download: about 18.6 GB
- Locdex status: **supported/default**
- Practical target: 32 GB system RAM; Locdex warns below 24 GB

### Kimi-distilled 9B — optional/experimental

- Upstream: `khazarai/Qwen3.5-9B-Kimi-k3-Distilled`
- Locdex GGUF: `mradermacher/Qwen3.5-9B-Kimi-k3-Distilled-GGUF`
- Quant: Q4_K_M
- Download: about 5.8 GB
- Locdex status: **experimental**
- Practical target: 16 GB system RAM

Both can be installed at the same time. Only the selected model is loaded for a session.

## Prerequisites

- Python 3.10+; Python 3.10-3.12 currently has the widest upstream prebuilt accelerated-runtime coverage.
- Git.
- Qwen: roughly 21 GB free disk including download/cache headroom; 32 GB RAM recommended.
- Kimi: roughly 8 GB free disk including download/cache headroom; 16 GB RAM recommended.
- Docker is not used in the current release. Candidate validation uses a disposable staged copy on the host.

Ollama is **not** required.

## Installation

```bash
git clone https://github.com/bandojayy/Locdex.git
cd Locdex
python -m pip install -e .
```

Then run the hardware-aware setup:

```bash
locdex setup
```

Or choose explicitly:

```bash
locdex setup --model qwen
locdex setup --model kimi
```

`locdex setup` installs a matching prebuilt local inference runtime, downloads the selected GGUF and smoke-tests it.

## Model management

```bash
locdex model list
locdex model status

locdex model install qwen
locdex model install kimi

locdex model use qwen
locdex model use kimi

locdex model remove qwen
locdex model remove kimi
```

The selection persists in Locdex's user config. `LOCDEX_MODEL=qwen|kimi` can override it for one process.

## Runtime management

```bash
locdex runtime status
locdex runtime install
locdex runtime repair
```

`runtime repair` forces reinstall of the currently detected prebuilt backend. The installer deliberately uses binary wheels only; it will report an unsupported configuration instead of silently invoking a local C/C++ toolchain.

Typical detected backends:

- Apple Silicon → Metal
- supported NVIDIA + CUDA → CUDA wheel matched to the detected driver capability
- Linux AMD ROCm → ROCm wheel
- Windows AMD → HIP Radeon when enabled with `LOCDEX_AMD_HIP=1`
- Linux/Windows with `vulkaninfo` available → Vulkan fallback
- otherwise → CPU

Set `LOCDEX_N_GPU_LAYERS=0` to force CPU or `LOCDEX_N_GPU_LAYERS=<integer>` to override automatic offload.

## Normal workflow

```text
$ locdex chat

> fix the empty-token authentication bug
[agent] reads relevant files
[agent] searches tests
[agent] edits src/auth.py directly
[agent] runs tests
[agent] inspects git diff
✓ Fixed empty-token handling. Tests passed.

> commit it
[agent] git status
[agent] git add ...
[agent] git commit -m "Fix empty-token authentication"
✓ Committed.

> push this branch
[agent] git push ...
✓ Pushed.
```

There is no mandatory `ship it` ceremony. `ship it` is just a convenience phrase that authorizes staging, committing and pushing when appropriate.

## Agent tools

Locdex exposes bounded tools to the local model instead of unrestricted Python access:

- list/search/read repository files;
- write or replace text files inside the workspace;
- delete files or empty directories;
- execute argv-style development commands with timeouts;
- run common test suites;
- inspect Git status and diffs;
- stage, commit, pull and push through dedicated Git tools.

Direct file access outside the workspace and `.git` internals is blocked. `run_command` cannot invoke `git`/`gh`; Git mutations go through dedicated tools so Locdex can enforce explicit user intent.

## Configuration overrides

```bash
export LOCDEX_MODEL=qwen                    # or kimi
export LOCDEX_MODEL_PATH=/absolute/path/model.gguf

export LOCDEX_MODEL_REPO='owner/model-GGUF'
export LOCDEX_MODEL_PATTERN='*Q4_K_M.gguf'
export LOCDEX_MODEL_REVISION='commit-or-tag'
export LOCDEX_MODEL_SHA256='expected_sha256_here'

export LOCDEX_N_CTX=16384
export LOCDEX_N_THREADS=8
export LOCDEX_N_GPU_LAYERS=auto             # auto is the default
```

## Optional cloud fallback

Locdex does **not** assume OpenRouter or any other cloud provider/model. Cloud fallback stays disabled until you explicitly configure it.

### OpenRouter

```bash
export LOCDEX_CLOUD_PROVIDER='openrouter'
export LOCDEX_CLOUD_MODEL='your-selected-provider/model'
export OPENROUTER_API_KEY='...'
```

### Anthropic directly

```bash
export LOCDEX_CLOUD_PROVIDER='anthropic'
export LOCDEX_CLOUD_MODEL='your-selected-claude-model'
export ANTHROPIC_API_KEY='...'
```

### Any OpenAI-compatible endpoint

```bash
export LOCDEX_CLOUD_PROVIDER='custom'
export LOCDEX_CLOUD_MODEL='your-selected-model'
export LOCDEX_CLOUD_BASE_URL='https://your-provider.example/v1/chat/completions'
export LOCDEX_CLOUD_API_KEY='...'
```

Use `LOCDEX_CLOUD_MODELS='model-a,model-b'` instead of `LOCDEX_CLOUD_MODEL` if you intentionally want a fallback chain. The local agent remains first; cloud escalation uses only the provider and model(s) you configured.

## Testing status

The bundle includes unit/regression coverage for agent editing, Git intent enforcement, model profiles, model manifests, hardware detection, prebuilt-runtime installation policy, router context and safety. These tests do not replace physical-machine acceptance testing.

See `TESTING.md` for the launch matrix.
