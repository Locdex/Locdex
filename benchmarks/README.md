# Locdex Benchmark and Qualification Protocol

## Scope

The `benchmarks/` directory contains versioned evaluation protocols and reviewed public results for the Locdex coding-agent runtime. Qualification probes and comparative benchmarks are separate evaluation categories.

**Qualification v1** is an installation/runtime acceptance check consisting of a fixed-output prompt and one bounded calculator-repair task. It measures whether a model/runtime can respond, invoke tools, preserve tests, and complete verification on a small fixture. It does not establish coding ability across languages, repositories, or task families. No aggregate performance claims follow from this probe.

**LocdexBench** is the planned broader evaluation suite. Benchmarks must be versioned, reproducible, and auditable before scores are published.

## Repository layout

- `results/` — reviewed, schema-validated public qualification records and future benchmark outputs
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
