# Maintainer Overlay Instructions

This file is for repository maintainers applying the generated upgrade bundle. It is not part of the end-user setup flow.

## Apply

1. Create a dedicated upgrade branch.
2. Copy the new files over the matching repository paths.
3. Preserve `.git/` and any repository files not explicitly replaced by the bundle.
4. Remove generated caches before reviewing the diff.
5. Run the complete automated test suite.
6. Run `python -m compileall src`.
7. Verify the CLI entry point with `locdex --help`.
8. Perform at least one real `locdex setup` hardware/runtime smoke test before merging.

Example:

```bash
git checkout -b docs-runtime-cleanup
pytest
python -m compileall src
locdex --help
```

## Generated caches

Do not commit:

```text
__pycache__/
.pytest_cache/
*.pyc
.venv/
venv/
```

## Legacy modules

Legacy modules may be removed only after the active import graph and regression suite confirm that no production path references them.

Candidate legacy modules from the previous architecture may include:

```text
consistency.py
rollback.py
updater.py
github_push.py
```

`editor.py`, `planner.py`, `memory.py`, `parser.py`, `validator.py`, `safety.py`, and the current runtime/agent modules must not be removed solely because their responsibilities changed.

## Post-overlay verification

Required checks:

```bash
pytest
python -m compileall src
locdex runtime status
locdex model list
locdex telemetry status
```

When a supported test machine is available:

```bash
locdex setup --model qwen
```

Run Kimi separately on a lower-memory or qualification machine:

```bash
locdex setup --model kimi
```

## Documentation consistency

Before merging, search the repository for stale product claims:

```text
Ollama
mandatory PR
PR only
never direct push
OpenRouter default
personal-name references
agenttool
```

Any remaining occurrence should be either intentionally historical or updated to the current architecture.
