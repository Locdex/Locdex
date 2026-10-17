# Locdex v1.4 Stable Release Roadmap

Locdex v1.4 is a single architecture progressing through prerelease testing toward a stable release. The alpha and stable builds share the same architectural direction; the prerelease supports testing, feedback and reliability improvements.

## Release status

| Release | Status | Purpose |
| --- | --- | --- |
| **v1.3.1** | Previous stable release | Established stable distribution |
| **v1.4.0a1** | Published prerelease | Public evaluation and compatibility testing of v1.4 |
| **v1.4.0** | Release candidate under review | Stable package versions prepared; pending end-to-end smoke verification and publication |

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

## Evaluation scope and release separation

[LocdexBench v0](../benchmarks/LOCDEXBENCH_DESIGN.md) is designed to measure verified coding outcomes, not merely model loading or a single smoke-test task. The first project-owned Python fixture, pinned manifest and baseline/reference/negative control validator are now implemented. An experimental container-isolated agent runner and preliminary infrastructure timing data are available. **The complete five-task LocdexBench suite, comparative model quality scores, and public leaderboard are deferred beyond v1.4 stable**; they are not a core product release prerequisite. The release still requires one functioning, verified agent task on declared supported hardware. Later benchmark phases cover repeated model comparisons, cloud-assisted attribution, cost and latency reporting, and statistical uncertainty.

The benchmark work is tracked in [GitHub Issue #15](https://github.com/Locdex/Locdex/issues/15). [Asynchronous model preload and warm worker reuse](https://github.com/Locdex/Locdex/issues/33) are tracked separately for post-v1.4 runtime optimization. Benchmark readiness does not imply that a leaderboard or comparative score is already available.

## Release channels

| Channel | Python package | npm package |
| --- | --- | --- |
| Published v1.4 test release | `locdex==1.4.0a1` | `@locdex/cli@1.4.0-alpha.1` via `next` |
| Target v1.4 stable release | `locdex==1.4.0` | `@locdex/cli@1.4.0` via `latest`, when published |

The existing alpha package versions remain immutable release identities. Version metadata for the **stable candidate branch** is aligned at 1.4.0, but stable artifacts, tags and distribution metadata are **not yet published**. See [release candidate notes](RELEASE_NOTES_V1_4_0.md) for the minimal acceptance gate.

The expanded [CI matrix](CI_MATRIX.md) provides Python and npm checks on Linux, Windows and macOS. These checks do not replace live model qualification.

For installation instructions, see the [local-model quickstart](QUICKSTART_LOCAL_MODELS.md). The [publishing specification](PYPI_RELEASE.md) describes the Python and npm release process. Sponsorship priorities and funding targets are listed in the [funding roadmap](FUNDING_AND_ROADMAP.md).
