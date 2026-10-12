# Getting Started with Locdex v1.4

`v1.3.1` is the previous stable release. `v1.4.0a1` is the published testing prerelease of the **same v1.4 architecture** being prepared for stable `v1.4.0`.

The recommended interface is the persistent coding-agent terminal. For the published v1.4 prerelease, see the [installation and local-model quickstart](docs/QUICKSTART_LOCAL_MODELS.md).

For contributors working from a source checkout:

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

Cloud inference requires explicit enablement and provider credentials. BASIC routing telemetry defaults to on with a first-run notice and immediate opt-out; no upload occurs without a configured HTTPS endpoint. RESEARCH telemetry is separately opt-in. Multi-agent workflows do not auto-commit or auto-merge.
