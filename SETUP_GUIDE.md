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

Cloud escalation additionally requires `workspace-network`; the default `workspace-write` sandbox will not send repository context to a provider.

## 6. Multi-agent orchestration

Agent YAML supports `depends_on`, `priority`, `role`, per-agent model, permission mode, sandbox mode, and write scope. Validate before running:

```bash
locdex agents validate --config agents.yaml
locdex agents run --config agents.yaml --parallel 2
```

Locdex does not auto-commit or auto-merge final results.

## 7. Telemetry and router training

Shared telemetry remains off by default:

```bash
locdex telemetry status
locdex telemetry preview
```

Train a lookup artifact from exported sanitized events:

```bash
locdex router train --input routing-events.jsonl --output router.json
```

This is offline training. Hands-on model/user qualification is intentionally a separate stage after the automated source/package gate.
