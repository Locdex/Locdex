# Locdex v1.4 Stable Release Roadmap

Locdex v1.4 is a single architecture progressing through prerelease testing toward a stable release. The alpha and stable builds share the same architectural direction; the prerelease supports testing, feedback and reliability improvements.

## Release status

| Release | Status | Purpose |
| --- | --- | --- |
| **v1.3.1** | Previous stable release | Established stable distribution |
| **v1.4.0a1** | Published prerelease | Public evaluation and compatibility testing of v1.4 |
| **v1.4.0** | Under development | Next stable release, pending acceptance criteria |

The public architecture is referred to as **Locdex v1.4**. Independently versioned components, such as the `rules-v0` router and benchmark schemas, do not define a separate product release.

## Architectural scope

The [v1.4 architecture](../ARCHITECTURE.md) separates two responsibilities.

**Agent:** Repository intelligence, task planning, context compilation, persistent sessions, permissions, sandbox policy, guarded tools, verification, model routing and rollback.

**Model runtime:** Hardware discovery, GGUF model management, local llama.cpp inference, adaptive inference limits and optional cloud-provider adapters.

Stabilization focuses on reliability, performance, testing and documented behavior rather than introducing a second architecture.

## Stable-release acceptance criteria

| Workstream | Qualification scope | Required evidence |
| --- | --- | --- |
| Local-model installation | Python/npm bootstrap, runtime backend selection, model downloads and resource constraints | Repeatable clean-install results and documented supported configurations |
| Interactive agent | Editing, steering, cancellation, session continuation and checkpoints | Regression tests and reviewed representative task outcomes |
| Security and change safety | Permission boundaries, sandbox reporting, Git guardrails, protected tests and rollback | Passing negative tests and platform-specific capability reporting |
| Model execution | Local inference limits, recovery, cloud opt-in and bounded context | Verified local-only behavior and controlled fallback tests |
| Evaluation | Versioned benchmark tasks, isolated runner and held-out grading | Reproducible baseline-fail, reference-fix-pass and incorrect-fix-fail checks |
| Packaging | Python wheel/sdist, npm launcher, release-tag alignment and upgrade paths | Passing release CI and fresh install/upgrade validation |
| Release readiness | Known issues, compatibility guidance and documentation | Reviewed release notes and approval of remaining risk |

These criteria describe the release gate; they are not assertions that every workstream has passed.

## Current evaluation priority: LocdexBench

[LocdexBench v0](../benchmarks/LOCDEXBENCH_DESIGN.md) is designed to measure verified coding outcomes, not merely model loading or a single smoke-test task. Initial milestones cover manifest validation, fixed fixtures, protected graders and isolated execution. Later phases introduce repeated cross-model comparisons, attribution of cloud-assisted completions, cost and latency reporting, and statistical uncertainty.

The work is tracked in [GitHub Issue #15](https://github.com/Locdex/Locdex/issues/15). Benchmark readiness does not imply that a leaderboard or comparative score is already available.

## Release channels

| Channel | Python package | npm package |
| --- | --- | --- |
| Published v1.4 test release | `locdex==1.4.0a1` | `@locdex/cli@1.4.0-alpha.1` via `next` |
| Target v1.4 stable release | `locdex==1.4.0` | `@locdex/cli@1.4.0` via `latest`, when published |

The existing alpha package versions remain immutable release identities. Stable artifacts, tags and distribution metadata will be published separately after the acceptance gate.

For installation instructions, see the [local-model quickstart](QUICKSTART_LOCAL_MODELS.md). The [publishing specification](PYPI_RELEASE.md) describes the Python and npm release process. Sponsorship priorities and funding targets are listed in the [funding roadmap](FUNDING_AND_ROADMAP.md).
