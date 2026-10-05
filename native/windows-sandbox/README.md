# Locdex Windows Sandbox Helper

This Rust executable is the native process-containment backend used by Locdex on Windows.

It currently provides:
- a restricted Windows access token with maximum privileges disabled;
- a Job Object with kill-on-close process-tree containment;
- explicit workspace/cwd validation before process creation.

It deliberately does **not** claim native filesystem ACL isolation or native network isolation yet. Those remain enforced by Locdex's higher-level sandbox/tool policy until the helper gains those capabilities.

Build on Windows:

```powershell
cd native/windows-sandbox
cargo build --release
$env:LOCDEX_WINDOWS_SANDBOX = (Resolve-Path .\target\release\locdex-windows-sandbox.exe)
locdex sandbox status
```

The helper reports machine-readable capabilities with:

```powershell
locdex-windows-sandbox capabilities
```
