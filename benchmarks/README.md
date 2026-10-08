# Locdex Benchmarks & Qualification Results

This is the public, reproducible landing page for Locdex's evaluation work.

**No benchmark claims are implied until real runs and full protocols are published.**

## Where to publish

1. **Canonical repository:** reviewed, versioned results go into `benchmarks/results/` on GitHub, with the tool version, exact model revision/quantization, workload, hardware tier, settings, timestamp, verified pass/fail outcome and any excluded runs in the accompanying experiment report.
2. **Reproducible datasets:** use a Hugging Face *dataset* repository under an official Locdex organization/account after the test cases and their licenses are ready. Dataset version/hash and evaluation code revision must be linked.
3. **Readable results:** make a website `/benchmarks` page backed by the reviewed datasets. Don't use it as the canonical raw evidence. Share release-level changelogs or technical articles linking the source.
4. **Independent comparisons:** only submit compatible scores to third-party leaderboards under their actual methodology; do not present Locdex's calculator check as a SWE-bench result.

## What is implemented now

The current command, `locdex model qualify <key>`, tests a deterministic prompt and optionally one simple calculator fix. Its output is a **qualification probe**, not LocdexBench. In particular, there is no statistically meaningful model ranking yet. The original private report can contain operating system details, paths and full diagnostics, so don't push it directly.

Export only sanitized public fields:

```powershell
locdex model qualify smoke --max-steps 8
# Copy the report_path from its JSON output, then:
locdex benchmark export --input "C:\path\to\private\qualification.json" --output "benchmarks/results/smoke-001.json"
locdex benchmark summary --dir benchmarks/results
```

Public exports include the suite identifier `locdex-qualification-v1`, model key, broad hardware tier, backend, status, timing and pass/fail indicators. Code, prompts, model text, raw hardware IDs and local filesystem paths are excluded. This is deliberately a *lossy* export. Before publishing, verify accuracy and add a public run-method note identifying the exact model artifact and model version/quantization without publishing private credentials or file paths.

## Required work before LocdexBench v1

- Establish a versioned, legally redistributable task suite with multiple languages and varied repository sizes; publish unmodified starting repositories, tests, grading scripts and task IDs.
- Run each model on consistent hardware and settings (or explicitly normalize and disclose limitations); record inference backend, quantization, context, step cap, tokens, costs, retries and timeouts.
- Use repeated trials / seeds for stochastic models. Publish success/failure totals, pass@1, verification success, wall-clock time, token/compute cost, denied-tool frequency and rollback results.
- Distinguish **local-only**, **cloud-only**, and **local → cloud** runs; count cloud handoffs/costs rather than crediting fallback successes to the local model.
- Version all run artifacts and report both median and distributional results (not just best runs). Preserve negative outcomes.
- Separate **user telemetry** from independent evaluation. Anonymous usage events alone can't establish comparative success rates or retained performance improvements.
- Do not publish API keys, original private repositories, proprietary code, user prompts or filesystem paths.

## Release process

Review generated `benchmarks/results/*.json` before merging; CI validates their strict schema. Once a sufficiently broad benchmark is built, publish a methodology, results CSV/JSON, scripts, seeds, and a signed release tag. The public GitHub repository remains the primary source; Hugging Face and a website are downstream mirrors. No real benchmark scores are included in this repository yet.
