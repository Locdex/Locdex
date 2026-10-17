# Locdex v1.4 local-model quickstart — stable candidate in review

**Version availability:** v1.3.1 is the previous stable release. Stable **v1.4.0 is a release candidate, not yet published**; the published **v1.4.0a1 prerelease** tests the same architecture. The installation commands below select the actually available testing prerelease until stable publication is confirmed.

Get Locdex running **locally**, with no Ollama and no cloud-model API key. Local model downloads are explicit; package installation alone does not download models or install `llama-cpp-python`. For the remaining stable release criteria, see [v1.4 development roadmap](V1_4_STABLE_ROADMAP.md).

## 1. Requirements

- Windows, macOS, or Linux with **Python 3.10–3.12** and Git
- Sufficient RAM and disk space for the selected GGUF model; CPU-only execution is supported but can be slow
- For the npm launcher, Node.js **18+**, plus one of the supported Python versions

Choose **one** installation route:

**PowerShell — install Python package in a project-independent virtual environment**

```powershell
py -3.11 -m venv .venv-locdex
.\.venv-locdex\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "locdex==1.4.0a1"
locdex --version
```

**macOS / Linux**

```bash
python3.11 -m venv .venv-locdex
source .venv-locdex/bin/activate
python -m pip install --upgrade pip
python -m pip install "locdex==1.4.0a1"
locdex --version
```

**npm v1.4 prerelease testing (Windows/macOS/Linux)**

```bash
npm install -g @locdex/cli@next --foreground-scripts
locdex --version
```

The npm wrapper creates its *own* managed Python environment, installs the exact matching PyPI package, and forwards `locdex` commands to that Python installation. Do **not** use `npm install -g @locdex/cli` without the `@next` tag while the alpha is not tagged `latest`.

## 2. Verify hardware and install the inference backend

```bash
locdex status
locdex runtime status
locdex runtime install --backend auto
locdex runtime verify
```

Locdex attempts to select a compatible prebuilt llama.cpp backend; availability depends on OS, architecture, Python version and acceleration support. Runtime installation is independent of GGUF downloads.

## 3. Pick and download a model

```bash
locdex model list
```

| Profile | GGUF download (approx.) | Minimum / recommended RAM | Recommended use |
| --- | --- | --- | --- |
| `smoke` — Qwen2.5-Coder 1.5B | 1.12 GB | 4 / 8 GB | Verify installation and small fixture tasks only |
| `qwen25-3b` — Qwen2.5-Coder 3B | 2.10 GB | 6 / 8 GB | Small experimental local tasks |
| `qwen25-7b` — Qwen2.5-Coder 7B | 4.68 GB | 8 / 12 GB | First real coding-agent qualification candidate |
| `qwen25-14b` — Qwen2.5-Coder 14B | 8.99 GB | 14 / 16 GB | Larger local coding tasks on suitable hardware |
| `qwen` — Qwen3.5 35B-A3B | 20.7 GB | 28 / 32 GB | Primary supported 32 GB-class model |

These figures describe model files/profile guidance, not tested throughput or guarantees. Budget additional space for downloads, Python and the working context. Other profiles are listed by `locdex model list`.

For a small-machine installation check:

```bash
locdex model install smoke
locdex model use smoke
locdex model status
locdex model qualify smoke --prompt-only
```

For a stronger coding-model candidate on sufficient RAM:

```bash
locdex model install qwen25-7b
locdex model use qwen25-7b
locdex model qualify qwen25-7b --prompt-only
```

The `--prompt-only` probe checks basic local inference. It is **not** a coding benchmark or a promise that the full agent will finish a task.

## Remove a local model and reclaim disk space

To remove a model that was downloaded through Locdex, first stop any active
agent or inference sessions using it. Then run:

```bash
locdex model remove smoke
locdex model status smoke
```

The removal command deletes the **actual GGUF downloads**, all cached revisions
and Hugging Face metadata **inside Locdex's managed cache for that model**, and
then clears its installation record. Other model profiles are left untouched.
Successful removal reports \`"removed": true\` and \`"installed": false\`.
A missing model reports \`"removed": false\`.

On Windows, a GGUF file may remain locked while an inference process is
running. Locdex now reports this error rather than incorrectly claiming
success or discarding the install record. Close the process and retry.

Externally provided paths through \`LOCDEX_MODEL_PATH\` and other applications'
shared Hugging Face caches are **not** deleted automatically; doing so could
delete user-managed or shared data. An external path must be managed
separately.


## 4. Run Locdex in a repository

```bash
cd path/to/your-project
locdex
```

In the interactive prompt, try:

```text
Inspect the failing tests and explain a minimal fix before editing files.
```

The default permission mode is `ask`. New sessions use the `workspace-network` capability sandbox (with separate permission checks), but **cloud inference remains disabled** unless explicitly enabled and configured. For no network access, type:

```text
/sandbox workspace-write
```

Then enter a task. For a one-shot local-only task that avoids network-capable commands:

```bash
locdex task --sandbox workspace-write --permission-mode auto-edit --task "Inspect the parser and fix the failing test."
```

Run `locdex model qualify qwen25-7b --max-steps 8` separately for a bounded coding-agent qualification fixture once prompt-only inference passes. This is not LocdexBench.

## 5. Troubleshooting and performance

```bash
locdex runtime status
locdex runtime verify
locdex model status
locdex inference budget --model smoke --max-tokens 32 --prompt-tokens 10
```

On very slow CPUs, the first cold model load/generation can take longer. Locdex uses separate adaptive inference deadlines; a single timeout means **the attempt failed**, not that the model is incapable of coding. Check the budget and choose an override if needed.

**PowerShell example (current terminal only):**

```powershell
$env:LOCDEX_INFERENCE_TIMEOUT_SECONDS = "180"
locdex model qualify smoke --prompt-only
Remove-Item Env:LOCDEX_INFERENCE_TIMEOUT_SECONDS -ErrorAction SilentlyContinue
```

Avoid publishing private qualification reports; use the sanitized `locdex benchmark export` workflow if you intentionally share results.

If `locdex` is not found after an npm install, check `npm prefix -g` and your executable PATH. If the npm alpha bootstrap fails, check that `locdex==1.4.0a1` is available in the same Python environment, your Python version is supported, and rerun `npm install -g @locdex/cli@next --foreground-scripts --loglevel=info`.

To remain entirely local, do not configure `LOCDEX_CLOUD_ENABLED` or any cloud provider. Models and generated files remain in their documented local folders unless tools approved by the user deliberately operate over the network.

For developer (editable source) installation, see [README — Development](../README.md#development).
