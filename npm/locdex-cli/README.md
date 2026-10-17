# Locdex

**An open-source, local-first coding agent for working inside software repositories.**

Locdex combines repository-aware context gathering, guarded file-editing tools, code verification, and local model inference. Cloud model providers can be configured separately when needed.

The `@locdex/cli` npm package is a **launcher for the Python Locdex runtime**, not a JavaScript reimplementation. During installation, it creates a dedicated Python environment and installs the corresponding version of the `locdex` Python package.

## Install

Requirements: **Node.js 18+**, **Python 3.10–3.12**, and Git. Local inference additionally requires enough RAM for the selected model.

```bash
npm install -g @locdex/cli --foreground-scripts
locdex --version
```

For the testing prerelease, use `npm install -g @locdex/cli@next --foreground-scripts` instead. The `latest` and `next` channels can resolve to different versions.

If automatic Python discovery fails, set `LOCDEX_PYTHON` to a supported Python executable before installing:

```powershell
$env:LOCDEX_PYTHON = "C:\\Python311\\python.exe"
npm install -g @locdex/cli --foreground-scripts
```

## Get started with a local model

The npm installer does **not** download a model or install the optional llama.cpp inference backend automatically. Set these up explicitly:

```bash
locdex status
locdex runtime install --backend auto
locdex runtime verify
locdex model list
locdex model install smoke
locdex model use smoke
```

The `smoke` profile is intended for installation checks, not reliable production coding. For larger repositories or substantive coding tasks, select a suitable model using the hardware guidance in `locdex model list`.

Start an interactive Locdex session from a repository:

```bash
cd my-project
locdex
```

Or use a single task:

```bash
locdex task --task "Investigate the failing tests and propose a minimal fix."
```

Locdex supports interactive progress, repository retrieval, permission prompts, verification, and checkpoints. Interactive sessions can preload a selected local model in a separate process and reuse the initialized model across sequential tasks. Local execution speed depends on model size, system memory, storage, and CPU/GPU capabilities.

## Optional cloud providers

Locdex can use configured cloud models, but cloud access is **not required** for local operation. Any cloud provider must be explicitly configured and authorized; model configuration does not bypass file permissions or sandbox policy.

See the [main documentation](https://github.com/Locdex/Locdex#readme) for provider setup and security behavior.

## Troubleshooting

If the command is unavailable after installation, verify the npm global executable directory is on `PATH` and try opening a new terminal.

```bash
locdex --version
locdex runtime status
locdex model status
```

If npm hides installation progress, use `--foreground-scripts --loglevel=info`. The package's Python bootstrap requires a working Python installation and access to PyPI. Model downloads and runtime installation are separate steps.

For issues, feature requests, documentation, and source code, visit [Locdex on GitHub](https://github.com/Locdex/Locdex).

**License:** MIT.
