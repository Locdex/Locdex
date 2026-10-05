# Start Here — Locdex v3.3

The primary product path is now the persistent coding-agent interface:

```bash
python -m pip install -e ".[dev]"
python scripts/preflight.py

cd path/to/project
locdex
```

Use `locdex task --task "..."` for one-shot automation, CI, and benchmarks.

Core v3.3 architecture now includes persistent sessions/checkpoints, same-terminal steering and approvals, sandbox/permission separation, Linux Bubblewrap support, a Windows native restricted-process helper, dependency-aware multi-agent worktrees, explicit local→configured-cloud escalation, and opt-in sanitized routing outcomes with offline lookup-artifact training.

Useful checks:

```bash
locdex sandbox status
locdex cloud status
locdex router status
locdex telemetry status
locdex model list
```

Windows native helper build:

```powershell
cd native\windows-sandbox
cargo build --release
$env:LOCDEX_WINDOWS_SANDBOX = (Resolve-Path .\target\release\locdex-windows-sandbox.exe)
```

Do not enable cloud fallback or shared telemetry implicitly. Both require explicit user configuration. Locdex never auto-commits or auto-merges multi-agent work.
