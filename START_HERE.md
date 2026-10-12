# Start Here — Locdex v1.4 (Stable Under Development)

`v1.3.1` is the previous stable release. `v1.4.0a1` is the published testing prerelease of the **same v1.4 architecture** being prepared for stable `v1.4.0`.

The primary product path is now the persistent coding-agent interface:

```bash
python -m pip install -e ".[dev]"
python scripts/preflight.py

cd path/to/project
locdex
```

Use `locdex task --task "..."` for one-shot automation, CI, and benchmarks.

The v1.4 architecture includes persistent sessions/checkpoints, same-terminal steering and approvals, sandbox/permission separation, Linux Bubblewrap support, a Windows native restricted-process helper, dependency-aware multi-agent worktrees, explicit local→configured-cloud escalation, and opt-in sanitized routing outcomes with offline lookup-artifact training.

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

Cloud fallback requires explicit enabling and provider credentials. BASIC telemetry is enabled by default with a visible opt-out but transmits nothing until a real HTTPS endpoint is configured; RESEARCH mode is separately opt-in. Locdex never auto-commits or auto-merges multi-agent work.
