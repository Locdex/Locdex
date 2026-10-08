# Locdex Testing

## Stage 0 — source/package gate

```bash
python -m pip install -e ".[dev]"
python scripts/preflight.py
```

The gate checks:

- all Python source/test files compile;
- every `locdex` module imports;
- unit tests collect and pass;
- wheel construction succeeds;
- required architecture files are present in the wheel;
- the built wheel installs into a temporary environment;
- the packaged `locdex --help` starts.

## Stage 1 — architecture smoke

```bash
locdex status
locdex models
locdex prepare --task "inspect this repository"
```

Verify context is bounded and the route is local-first.

## Stage 2 — cloud Context Gateway smoke

```bash
locdex prepare --task "password=supersecret fix auth" --cloud
```

Verify that the output reports at least one redaction and does not expose the secret value.

## Later stages

Runtime/model, tool execution, Git, provider APIs, benchmarks, and platform qualification come after the source/package gate.


## Routing/telemetry qualification

Before enabling a production telemetry endpoint:

- prove telemetry is disabled by default;
- prove no endpoint means no network call;
- fuzz unknown fields and verify fail-closed rejection;
- inspect `locdex telemetry preview` for forbidden data;
- test batch failure/requeue behavior;
- test router rules with local-only, balanced, fast, quality, cost, and provider constraints;
- test session switching penalties and verification-failure escalation boundaries;
- test learned artifact checksum/parse/fallback behavior;
- evaluate calibration (`predicted_success` vs observed success) on held-out LocdexBench cases.

A learned router may only replace `rules-v0` after it beats or matches the current router on held-out quality while meeting cost/privacy regressions defined for the release.


## v3.3 automated coverage

The automated gate now additionally covers:

- Windows native-helper discovery/capability reporting and command wrapping;
- permission prompt reason/access metadata;
- dependency validation and downstream worktree inheritance;
- CLI parsing for cloud status and offline router training;
- versioned lookup-artifact training.

The Windows helper has a dedicated Windows GitHub Actions build/probe workflow.

## Deferred hands-on qualification

Interactive feel, real local-model behavior, permission-prompt ergonomics under live generation, Windows helper execution on the target machine, and provider escalation with a real account are intentionally left for the later hands-on session. Do not treat automated unit coverage as evidence that those UX/model qualifications are complete.


## Interactive activity / installation progress coverage

Unit tests cover event-driven activity text, missing/stale model activity, tool completion counts, bounded output, model SHA-256 progress wiring, and pip runtime progress flag. The CI matrix also imports the packaged CLI. Real Windows terminal redraw and actual multi-GB download throughput still require a manual device run.

## Interactive Windows display and bounded inference

`tests/test_interactive_runtime.py` checks that the prompt renders progress and a complete approval choice panel above the input, that the permission broker unblocks after an approval, and that a non-responsive isolated model process is terminated on timeout or cancellation. `tests/test_interactive_exit.py` verifies exit/Ctrl+C semantics. Manual VS Code PowerShell validation is still needed because headless CI cannot certify terminal redraw and keyboard behavior.


## Adaptive native inference and cloud fallback

`tests/test_adaptive_timeout.py` checks model-size/hardware/context-dependent budget estimates, explicit overrides, accelerated limits when cloud is permitted, and local-only calibration. `tests/test_cloud_timeout_fallback.py` checks that native timeouts are converted to local outcomes, cloud execution succeeds with explicit configuration and network-enabled sandbox, cloud remains unavailable when policy blocks it, and cancellation never escalates. Headless tests are not a substitute for real model/hardware benchmarking.
