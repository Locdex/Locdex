# Start the Locdex v3.1 Build

This is the main public Locdex repository baseline. It contains no private enterprise implementation.

## On the new architecture branch

1. Keep `.git/` and your repository license.
2. Replace the old public source/test/docs with this bundle.
3. Do not copy the separate private `locdex-enterprise` scaffold into the public repo.

Recommended clean replacement from the repository root:

```bash
rm -rf src/locdex tests scripts
```

Then copy this bundle's `src/locdex`, `tests`, `scripts`, docs, `pyproject.toml`, and `.gitignore` into the repo root.

Windows PowerShell equivalent:

```powershell
Remove-Item -Recurse -Force src\locdex
Remove-Item -Recurse -Force tests
Remove-Item -Recurse -Force scripts
```

## First commands

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/preflight.py
```

Windows PowerShell activation:

```powershell
.venv\Scripts\Activate.ps1
```

Expected final line:

```text
ALL PREFLIGHT CHECKS PASSED
```

## First architecture smoke

```bash
locdex status
locdex models
locdex prepare --task "inspect this repository and explain the main CLI path" --repo .
```

Then test the cloud-safe Context Gateway without making a network call:

```bash
locdex prepare --task "password=temporary-secret debug auth" --repo . --cloud
```

The output should report redaction(s), and the secret value should not appear in the compiled Context Pack.

## What comes next

This baseline establishes the frozen v3.1 boundaries and a runnable/packageable public project. The next implementation sequence is:

1. runtime installer/backends;
2. GGUF model manager and checksum/download flow;
3. Qwen local inference;
4. unchanged Kimi experimental inference;
5. full agent tool loop;
6. deterministic verification pipeline;
7. provider adapters + progressive cloud retrieval;
8. cost accounting/prompt caching;
9. benchmark and hardware qualification.


## Routing/telemetry smoke checks

```bash
locdex route --task "fix a failing Python unit test" --repo .
locdex router status
locdex telemetry status
locdex telemetry preview
```

Do not enable shared telemetry until the private ingestion endpoint is deployed. Once it exists:

```bash
locdex telemetry endpoint https://telemetry.locdex.dev/v1/events
locdex telemetry enable
```
