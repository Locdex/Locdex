# Locdex Benchmark and Qualification Protocol

## Scope

The `benchmarks/` directory contains versioned evaluation protocols and reviewed public results for the Locdex coding-agent runtime. Qualification probes and comparative benchmarks are separate evaluation categories.

**Qualification v1** is an installation/runtime acceptance check consisting of a fixed-output prompt and one bounded calculator-repair task. It measures whether a model/runtime can respond, invoke tools, preserve tests, and complete verification on a small fixture. It does not establish coding ability across languages, repositories, or task families. No aggregate performance claims follow from this probe.

**LocdexBench** is an evaluation workstream for v1.4 stable development. The [evaluation protocol](LOCDEXBENCH_DESIGN.md) covers task fixtures, execution isolation, independent grading, result attribution and reporting. A first **owned Python test fixture, strict manifest validator and reference-control check** are available. An **experimental Docker-only local trial runner** is available at [LOCAL_RUNNER.md](LOCAL_RUNNER.md), but live model qualification, a multi-task comparative suite and public leaderboard are **not yet available**; no scores have been published.

## Preliminary v0 diagnostic figures (17 October 2026)

The first [measured local CPU / Docker storage figures](RESULTS_V0_PRELIMINARY.md) are available with a loading-time comparison graphic. On one Windows CPU-only setup, loading Qwen2.5-Coder 3B from a Windows file bind mount took **816.3s**, versus **76.7s** from Docker-native storage (**10.6× faster**); first copy into Docker storage took **267.5s**. These are **single-run infrastructure measurements**, not benchmark task-success scores. The pinned fixture controls passed, but the latest end-to-end local agent trial still timed out **before the first decision**. No completed coding benchmark score has been published.

## LocdexBench v0 — audited fixture controls

The first reviewed task is `py-arithmetic-edge-001` in `tasks/`. Its baseline is pinned to a full Git commit SHA. The coding task lives in `fixtures/`; the held-out grader and gold/negative controls live separately in `graders/` and `references/`. The fixture validator checks the pinned source against Git, then verifies that the buggy baseline fails, the reference fix passes, and the negative control is rejected.

```bash
python scripts/validate_benchmark_fixtures.py
python -m pytest tests/test_benchmark_v0.py
```

The commands above run *only a reviewed, repository-owned fixture* on the CI host. **They are not a general benchmarking runner, model evaluation, or a safe way to execute downloaded repositories.** The validator fails closed on manifest path traversal, unexpected commands, additional write scopes, unsupported fields, changed pinned fixtures and missing external graders.

A first **experimental local-only Docker runner** now enforces a network-disabled agent container, separate grading container, protected-file verification and bounded metadata output. See [LOCAL_RUNNER.md](LOCAL_RUNNER.md) for prerequisites and limitations. The live GGUF execution path has not been certified on representative hardware. Cloud/hybrid comparisons and full benchmark reporting are pending. See [Issue #15](https://github.com/Locdex/Locdex/issues/15).

## Repository layout

- `results/` — reviewed, schema-validated public qualification records and future benchmark outputs
- `LOCDEXBENCH_DESIGN.md` — v0 protocol proposal and phased implementation gates
- `src/locdex/benchmark/publish.py` — strict privacy-preserving qualification export and public-record validation
- `tests/` — regression tests for qualification and benchmark reporting

Private qualification reports are written to the local Locdex application cache. They can include paths, system details, and diagnostic output and must not be committed directly.

## Reproducing a qualification run

Requires an installed local model and a healthy llama.cpp runtime.

```powershell
locdex model qualify smoke --max-steps 8
locdex benchmark export --input "PATH_TO_PRIVATE_REPORT" --output "benchmarks/results/smoke-001.json"
locdex benchmark summary --dir benchmarks/results
```

The export schema is `locdex-qualification-v1`. Exported fields are limited to model profile, broad hardware tier, runtime backend, elapsed time, step count, verification results, test preservation, and probe pass/fail outcomes. Raw code, prompts, responses, repository paths, machine identifiers, and credentials are excluded.

Qualification results may be published only after verifying the record against its source run and reporting failures as well as successes.

## Requirements for comparative results

Each benchmark release must identify:

1. Suite version, task set, fixture checksums, permitted licenses, starting repository states, grader scripts, and evaluation source revision
2. Exact model and quantization, sampling parameters, inference backend, context constraints, tool permissions, step ceilings, and timeout policy
3. Hardware class, RAM/VRAM availability, concurrency, and cost assumptions
4. Repeated trials where relevant, complete attempt counts, failures, exclusions, and statistical uncertainty
5. Verification outcome, task success, wall-clock time, token usage, estimated API cost, and rollback/cancellation behavior
6. Routing category: local-only, cloud-only, or local-to-cloud. Cloud completions must not be credited to local-model-only performance

Production telemetry provides observational routing data; it is not a substitute for controlled paired benchmarking.

## Publication

GitHub remains the canonical versioned source for evaluation code, methodology, and reviewed result artifacts. Approved redistributable task datasets may be mirrored to a versioned Hugging Face dataset repository. A website leaderboard may visualize these records after the methodology and source data are publicly available.

Public artifacts must be inspected for proprietary code, credentials, paths, model-response excerpts, and other unintended disclosures before publication. The benchmark CI workflow validates the public result schema.


## Slow-hardware qualification caveat

Qualification is not a timed benchmark of model quality when a run exhausts its inference budget. The timeout policy estimates separate load and generation deadlines from hardware, model size, context and local performance observations. Initial runs on older CPU-only systems may have longer cold-start deadlines and can still time out. A timed-out prompt check is recorded as `prompt_failed`, with the agent probe unattempted. Do not combine such runs with a previously recorded `agent_probe_failed` attempt or infer comparative coding quality from a single timeout.
