# Locdex v1.4.0 — stable release candidate notes

**Status: release candidate in review. Not yet a published GitHub/PyPI/npm release.**

Locdex v1.4.0 advances the open-source local-first coding agent architecture established by the v1.4 alpha. The stable candidate is prepared with aligned Python and npm versions, bounded guarded coding tasks, local-model management, explicit cloud escalation, permission controls, repository context tools, verification, and recoverable changes.

## What is included

- **Repository-aware agent:** structured tasks, targeted source retrieval, multi-step local model tool decisions, permission prompts, bounded execution, verification and change rollback.
- **Local and optional cloud runtime:** managed GGUF model profiles and separate inference backend installation; cloud escalation remains opt-in with provider configuration and permission policy.
- **Interactive warm model worker:** one isolated llama.cpp child begins loading before the first interactive task, reports a nonblocking worker state, reuses initialized weights across sequential tasks and unloads on model switching or CLI exit. One-shot `locdex task` invocations still have a cold-start cost.\n- **Safety and observability:** task progress, verification evidence, sandbox capability reporting, constrained tool access, and protected test behavior.
- **Experimental LocdexBench v0 infrastructure:** first pinned Python fixture, visible/held-out grading controls, offline Docker runner, and checksum-verified GGUF model caching in Linux-native Docker volumes. [Preliminary hardware findings](../benchmarks/RESULTS_V0_PRELIMINARY.md) are **diagnostics only**, not benchmark task-completion scores.
- **Distribution:** Python package `locdex==1.4.0` and npm wrapper `@locdex/cli@1.4.0`, with npm pinning the exact Python release. Publishing is pending the release approval and successful artifact checks.

## Hardware and runtime qualifications

Local models need sufficient **system RAM and memory bandwidth** in addition to disk space. Model file size alone is not a complete RAM requirement: llama.cpp also allocates inference buffers and context/KV cache. CPU-only execution is supported but may be slow, especially with low system memory or disk paging. `qwen25-3b` remains an **experimental 8 GB-class model profile** and is not a promise of acceptable throughput on every 8 GB laptop.

On one older Windows CPU-only setup (Intel Core i5-5200U; ~7.72 GiB host RAM, ~3.69 GiB Docker Linux VM memory) Qwen2.5-Coder 3B Q4_K_M at 4096 context took **816.3s** to initialize through a Windows bind mount and **76.7s** from a Docker-native volume. These are exploratory single-run load timings; the coding-agent task did not reach successful grading on that setup. See [complete limitations](../benchmarks/RESULTS_V0_PRELIMINARY.md). Docker benchmarking is optional; normal native Windows/Linux/macOS interactive usage does not require Docker.

## Out of scope for v1.4.0

- Public comparative LocdexBench leaderboard, five-task benchmark suite, and a claim of verified model coding accuracy.
- Cross-process model daemon for independent one-shot commands, configurable idle eviction and shared warm workers across terminals. Interactive sessions already support process-local asynchronous preload and warm reuse; additional runtime optimizations remain tracked in [issue #33](https://github.com/Locdex/Locdex/issues/33).
- Guaranteed filesystem and network isolation for all native Windows/macOS sandbox configurations. Consult platform capability reporting before allowing untrusted repositories.

## Release gate and approval checklist

- [ ] CI passes on Python 3.10/3.11/3.12 and Windows/Linux/macOS; npm wrapper checks pass.
- [ ] Version agreement: `pyproject.toml`, `src/locdex/__init__.py`, npm package version, and npm Python pin.
- [ ] Build wheel and sdist; validate metadata, then test fresh `pip install` of the resulting wheel.
- [ ] Complete **one successful end-to-end agent task with verification** on a declared supported machine and an explicit model/provider configuration. The task need not be part of LocdexBench. Record task outcome, hardware, model, steps and any remaining limitations.
- [ ] Confirm permissions, rollback, cloud-off behavior and relevant basic security regressions.
- [ ] Publish an approved tag `v1.4.0` and **non-prerelease** GitHub Release. GitHub Trusted Publishing then publishes the matching PyPI package.
- [ ] Confirm PyPI `locdex==1.4.0` is available, publish npm `@locdex/cli@1.4.0` as `latest`, and validate both fresh installations.

**Do not claim that the v1.4 stable release is public until its GitHub, PyPI and npm records are confirmed.** A clean CI matrix alone is not a substitute for a working agent task.
