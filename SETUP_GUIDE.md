# Locdex Setup Guide

## 1. Create the environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 2. Run the mandatory package gate

```bash
python scripts/preflight.py
```

Do not begin model/runtime qualification until the gate is green.

## 3. Inspect hardware and models

```bash
locdex status
locdex models
```

## 4. Exercise the new context/routing path

```bash
locdex prepare --task "find the authentication flow" --repo .
```

To test cloud-context compilation and secret redaction without calling any provider:

```bash
locdex prepare --task "debug token=secret123 in auth" --repo . --cloud
```

This does not call a cloud API. It only compiles the cloud-safe Context Pack.

## 5. Next implementation stages

After the source/package gate:

1. local runtime installer;
2. model download/verification;
3. Qwen inference backend;
4. Kimi inference backend;
5. tool execution loop;
6. deterministic verifier;
7. cloud provider adapters and cost accounting;
8. benchmarks and hardware matrix.
