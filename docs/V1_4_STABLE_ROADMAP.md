# Locdex v1.4 — stable release under development

**This is one v1.4 architecture and one stabilization cycle.** The public alpha is a preview/testing build of the same codebase and architectural direction—not a separate architecture release.

| Release | Status | Purpose |
| --- | --- | --- |
| **v1.3.1** | **Published stable** | Last released stable version of Locdex |
| **v1.4.0a1** | **Published prerelease** | Test the v1.4 architecture, collect reproducible bugs and compatibility evidence |
| **v1.4.0** | **Under development (not yet published)** | Complete the v1.4 stabilization and validation process and then ship the full stable release |

**Naming rule:** All public product and architecture documentation calls this release family **Locdex v1.4**. Internal component-specific schemas such as `rules-v0` and benchmark manifest versions remain separately versioned, but there is no competing product architecture number.

## What is included in the v1.4 architecture

The v1.4 system retains a clear **Agent / Model Runtime** boundary. The agent owns repository intelligence, context construction, task state, guarded tools, permissions, rollback, verification and routing. The runtime owns hardware detection, local GGUF model management, llama.cpp inference lifecycle/adaptive budgets, and explicitly configured cloud-provider adapters.

The goal between **v1.4.0a1** and **v1.4.0 stable** is to **validate and harden those same components**, correct defects, complete missing acceptance work, and demonstrate usable coding outcomes. We are **not** planning to replace the architecture merely because the prerelease number changes.

## Development work before v1.4 stable

| Area | Work remaining | Stable acceptance criteria |
| --- | --- | --- |
| **Local-model setup** | Diagnose Windows/macOS/Linux backend issues, low-resource machine timeouts, model download and startup failures | Clean installation paths; selected models load/qualify on representative hardware; known exceptions documented |
| **Agent reliability** | Validate real edits, permissions, sandbox controls, cancellation, rollback, and session recovery | Regression tests and manually reviewed task traces, including interrupted and failed tasks, pass without unsafe or unverified mutations |
| **Routing and cloud economics** | Validate evidence-first local-to-cloud escalation, context limits, provider handling, attribution and cost | Explicit opt-in; bounded source handoff; reproducible escalation tests; no cloud calls during local-only qualification |
| **LocdexBench (next major development task)** | Implement versioned task schema, audited fixtures, isolated runner and held-out grading | At least one full end-to-end repeatable fixture with fail-before/fix-after/negative controls; expand to a reviewed pilot before comparative claims |
| **Packaging and docs** | Keep the prerelease test install separate; review npm and PyPI releases and platform setup | Stable `1.4.0` metadata only after release approval; exact matching Python/npm versions and verified clean installs |
| **Release review** | Triage alpha feedback, remaining bugs, known limitations, security/regression checks | Core CI and release artifacts pass; documented blockers resolved or explicitly accepted; review approves stable release |

**The v1.4 stable release is not complete until all agreed release gates are evidenced and approved.** The table is a development checklist, not a declaration that all milestones have passed. Benchmark scores must never be fabricated.

## Next engineering milestone: LocdexBench

Start with [LocdexBench v0 specification](../benchmarks/LOCDEXBENCH_DESIGN.md) and [Issue #15](https://github.com/Locdex/Locdex/issues/15). First implement a manifest validator, one pinned Python fixture and an out-of-agent-workspace hidden grader; then a safe disposable runner. Report failures, resource budgets and local/cloud/hybrid attribution honestly. This provides objective evidence about v1.4's *agent behavior* before a general stable launch.

## Release and branch rules

- **While under development:** documentation titles refer to **Locdex v1.4 (stable under development)**, with `v1.4.0a1` described as its published alpha/test release.
- **Released package metadata stays accurate:** source currently identifies `1.4.0a1` because those bits were published. Do not rewrite the alpha tag or pretend `v1.4.0` is available.
- **When stable is ready:** update `pyproject.toml` to `1.4.0`; update npm's `package.json` to `1.4.0` and its Python install pin to `locdex==1.4.0`; update matching tests; verify CI and clean installs; create a new `v1.4.0` GitHub release, PyPI distribution and npm stable publication.
- Keep the already published `v1.4.0a1` release and its historical notes intact. Do not repurpose, overwrite or retag it as stable.

For more detail see [architecture](../ARCHITECTURE.md), [quickstart](QUICKSTART_LOCAL_MODELS.md), [funding roadmap](FUNDING_AND_ROADMAP.md), and [PyPI release procedure](PYPI_RELEASE.md).
