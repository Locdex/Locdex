# Locdex Setup Guide — v3.3

## 1. Development environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/preflight.py
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/preflight.py
```

## 2. Primary interactive workflow

```bash
cd path/to/project
locdex
```

`locdex task --task "..."` remains the headless/script/CI primitive. During an interactive run, type ordinary text to steer it, `/status` to inspect the session, or `/cancel` to stop it.

## 3. Runtime and model

```bash
locdex status
locdex runtime install --backend auto
locdex runtime verify
locdex model list
locdex model install qwen25-7b
locdex model use qwen25-7b
```

## 4. Windows native sandbox helper

The Python package works without the helper, but Windows then reports `backend=logical`.

Build the native process-containment helper on Windows:

```powershell
cd native\windows-sandbox
cargo build --release
$env:LOCDEX_WINDOWS_SANDBOX = (Resolve-Path .\target\release\locdex-windows-sandbox.exe)
locdex sandbox status
```

The current helper supplies restricted-token + Job Object process containment. It does not yet claim native filesystem or network isolation.

## 5. Optional cloud fallback

Cloud use is disabled unless all required values are supplied:

```powershell
$env:LOCDEX_CLOUD_ENABLED = "1"
$env:LOCDEX_CLOUD_PROVIDER = "configured-provider"
$env:LOCDEX_CLOUD_MODEL = "provider-model-id"
$env:LOCDEX_CLOUD_BASE_URL = "https://provider.example/v1"
$env:LOCDEX_CLOUD_API_KEY = "..."
locdex cloud status
```

Optional cost metadata:

```text
LOCDEX_CLOUD_INPUT_COST_PER_MILLION
LOCDEX_CLOUD_OUTPUT_COST_PER_MILLION
LOCDEX_CLOUD_CONTEXT_LIMIT
```

New sessions default to `workspace-network`, but cloud calls still require `LOCDEX_CLOUD_ENABLED=1` and explicit provider credentials. Existing sessions preserve their saved sandbox configuration. Set `/sandbox workspace-write` to disable network access.

## 6. Multi-agent orchestration

Agent YAML supports `depends_on`, `priority`, `role`, per-agent model, permission mode, sandbox mode, and write scope. Validate before running:

```bash
locdex agents validate --config agents.yaml
locdex agents run --config agents.yaml --parallel 2
```

Locdex does not auto-commit or auto-merge final results.

## 7. Telemetry and router training

BASIC telemetry is enabled by default (with opt-out); RESEARCH remains separate:

```bash
locdex telemetry status
locdex telemetry preview
```

Train a lookup artifact from exported sanitized events:

```bash
locdex router train --input routing-events.jsonl --output router.json
```

This is offline training. Hands-on model/user qualification is intentionally a separate stage after the automated source/package gate.


## Interactive activity and install progress

Inside `locdex`, active tasks now show an animated status bar and real-time tool-action log while typing or steering remains available. The bar counts actual tool completions; model thinking is not exposed as fake reasoning or a percentage. Run `locdex model install qwen25-7b` for real byte-based model download and checksum progress, or `locdex runtime install --backend auto` for pip wheel transfer percentages and runtime validation. npm installation can hide lifecycle logs unless `--foreground-scripts` is passed:

```powershell
npm install -g @locdex/cli --foreground-scripts --loglevel=info
```


## Exit, Ctrl+C and approval handling

PowerShell: run `locdex` inside your project. Enter `exit`, `quit`, `/exit`, or `/quit` to close the idle chat. During a task, the same commands request cancellation and close the chat when the operation stops. `/cancel` and Ctrl+C request normal cancellation. If a native model call does not yield, a second Ctrl+C within four seconds after the first (not an immediate duplicate) forces the process to terminate, but rollback cannot be guaranteed. Permission requests reuse the active prompt rather than cancelling its input task.

## Windows troubleshooting: activity, approval and timeouts

Pull the latest source and reinstall the development build, then launch from the test project. The activity and approval panels appear above the text input. A short permission question and labeled choices must be visible together; `y` allows once and `a` allows similar actions for the session. The interactive model process uses independently calculated load/generation deadlines based on model size, hardware capacity and locally measured inference speed. Timeouts terminate that process and produce a recoverable failure. Cloud fallback requires configured inference credentials and the `workspace-network` sandbox; telemetry credentials alone cannot provide cloud inference.

```powershell
cd C:\Users\Ade\Documents\Repositories\locdex\Locdex
git pull origin architecture-v3.2-ready
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/preflight.py
cd C:\Users\Ade\Documents\locdex-agent-test
locdex
```

The 12-step agent cap is a number of iterations, **not** a timeout. Interactive local inference runs inside a killable process so a native model call cannot freeze the entire terminal. The smoke model is only a development/testing model, not a reliable coding model.


## Adaptive timeout and cloud recovery

Use `locdex inference budget --model smoke` (or `--model qwen25-7b --max-tokens 512`) to inspect estimated local time budgets. The first run uses a bounded hardware/model heuristic; successful inference updates a **local-only** speed cache, making later estimates better grounded. To override the estimate in PowerShell: `$env:LOCDEX_INFERENCE_TIMEOUT_SECONDS = "120"` before launching `locdex`. Explicit overrides supersede the automatic cloud-accelerated deadline.

When a local inference times out, Locdex can retry via a configured OpenAI-compatible provider **only if** `locdex cloud status` reports `enabled: true` and the interactive session is switched to `/sandbox workspace-network`. No cloud retry occurs on user cancellation. A telemetry-only Worker does not supply model inference. Fallback transmits task/context to the user-configured inference provider and may incur API charges.

## Provider selection and public results

```powershell
locdex cloud providers
locdex cloud status
locdex benchmark summary --dir benchmarks/results
```

To configure cloud fallback in PowerShell, set `LOCDEX_CLOUD_ENABLED=1`, `LOCDEX_CLOUD_PROVIDER`, `LOCDEX_CLOUD_MODEL`, and the provider-specific API key environment variable. Use native Anthropic (`ANTHROPIC_API_KEY`) or OpenAI-compatible endpoints for OpenAI, Gemini, Groq, OpenRouter, DeepSeek, Together, Mistral, and custom services. `LOCDEX_CLOUD_API_KEY` overrides individual provider keys, so unset it when switching services. API keys are read only from environment variables, never written into project files.

For benchmarks, run `locdex model qualify <model>`, then review the returned `report_path`. Use `locdex benchmark export --input <report_path> --output benchmarks/results/<run>.json` and `locdex benchmark summary --dir benchmarks/results`. Publish only reviewed sanitized results and clearly label these as qualification probes rather than LocdexBench scores.

## Network permissions, evidence collection and qualification errors

New sessions default to `workspace-network`; network is available only through the existing permission and tool-policy checks. Network capability does not enable cloud billing or cloud inference. Old sessions keep their saved sandbox mode, which can be updated with `/sandbox workspace-network`.

Before the first cloud fallback request, Locdex assembles a bounded, locally generated evidence pack from relevant source, dependency context and failure diagnostics. The cloud agent avoids repeated broad repository context in its initial prompt. API execution is only attempted after that local work completes, and only when cloud credentials are configured.

`locdex model qualify smoke --max-steps 8` uses isolated model inference for both probe phases. A model timeout is recorded as a failed qualification, and Ctrl+C produces an interrupted report rather than a native inference stack trace. Run `locdex inference budget --model smoke` to inspect the local deadline estimate.


### CPU-only qualification on low-memory laptops

A cold inference call on a dual-core Windows CPU with limited available RAM may need substantially more than 35 seconds even for a 1.5B Q4 model. The automatic timeout policy applies slower-hardware minimums and maintains a local-only history of genuinely timed-out phases to avoid repeatedly selecting an insufficient deadline.

```powershell
locdex inference budget --model smoke --max-tokens 32 --prompt-tokens 10
locdex model qualify smoke --prompt-only
```

If repeated timeouts occur, a manual override can be used for a controlled experiment:
```powershell
$env:LOCDEX_INFERENCE_TIMEOUT_SECONDS = "180"
locdex model qualify smoke --prompt-only
Remove-Item Env:LOCDEX_INFERENCE_TIMEOUT_SECONDS -ErrorAction SilentlyContinue
```

A prompt failure is not a claim about coding-agent performance. `benchmarks/results/` may contain results from older runs; those should remain unchanged and be labeled independently.
