# Continuous Integration — Locdex v1.4

The stable-release CI pipeline validates Python functionality, packaging, npm bootstrap and approved benchmark fixture controls across supported development platforms.

## Automated jobs

| Check | Platform | Scope |
| --- | --- | --- |
| Python preflight | Ubuntu / Python 3.10, 3.11, 3.12 | Imports, tests, wheel, clean installation |
| Python preflight | Windows / Python 3.11 | Same Python release gates |
| Python preflight | macOS / Python 3.11 | Same Python release gates |
| npm bootstrap | Ubuntu, Windows, macOS / Node.js 20 and Python 3.11 | Syntax, tarball dry run, Python launcher bootstrap |
| Benchmark controls | Ubuntu / Python 3.11 | Schema validation, pinned fixture, baseline/reference/negative outcomes |
| Windows native sandbox | Windows / Rust stable | Native helper build and capability probe |

The main CI workflow runs on pull requests and pushes to `main`. Benchmark-control checks run on benchmark-related changes. The native helper workflow is restricted to its code and workflow changes.

## Limits

- The benchmark-control job executes a **reviewed, project-owned fixture**, never arbitrary downloaded repositories or agent-generated patches.
- LocdexBench's general-purpose isolated agent runner is a separate unfinished workstream. It must not be represented as shipped.
- GitHub-hosted runners do not replace testing on real end-user Windows, macOS and Linux machines with local GGUF models and varying RAM/VRAM.
- Windows native process containment does not currently guarantee filesystem or network isolation; the macOS backend remains policy-based.
- A green test suite does not establish a model's general coding quality, routing accuracy, inference performance or cloud-provider reliability.

See the [stable-release roadmap](V1_4_STABLE_ROADMAP.md) and [benchmark protocol](../benchmarks/LOCDEXBENCH_DESIGN.md).
