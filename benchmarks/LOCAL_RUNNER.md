# LocdexBench v0 — Isolated Local Trial Runner

**Status:** Experimental local-only runner. It is a development tool, **not** a public leaderboard, and no model scores have been released. The live Docker/GGUF path still requires validation on representative hardware before stable v1.4.

## Isolation model

A benchmark attempt uses three separate processes:

1. A **disposable Git workspace** containing only an audited and commit-pinned fixture, never the grader or reference patches.
2. A **locked-down Docker agent container** with the workspace as its sole writable bind mount and a selected GGUF model as a read-only file. Networking is disabled, Linux capabilities dropped, root filesystem read-only, process/memory/CPU limits applied, and cloud inference plus telemetry uploads disabled.
3. A **separate grading container** with the candidate workspace mounted read-only. The held-out grader is mounted only into the grading container; it is never accessible to the agent.

The runner checks changed files against the explicit per-task allowlist before grading. A timed-out or failed attempt does not receive a pass. No local subprocess fallback is available if Docker or the pinned image is missing.

A task's fixed baseline and gold/negative controls are validated separately by `python scripts/validate_benchmark_fixtures.py`. That command only executes reviewed repository-owned tests, not arbitrary model output.

## Prerequisites

- A Docker engine capable of running Linux containers.
- A **preloaded, immutable Docker image** identified by full `sha256:` image ID or a repository digest. The image must contain Python 3.10–3.12, Git, the matching Locdex Python core, and a working `llama-cpp-python` backend. No image is downloaded by the runner.
- A local GGUF model file that matches the chosen built-in Locdex profile. The single model file is mounted read-only. A model file hash is recorded.
- A clean Locdex source checkout containing the recorded fixture Git commit. The runner verifies this automatically.

The standard `locdex==1.4.0a1` Python package and `@locdex/cli@1.4.0-alpha.1` are the published testing prerelease. Stable v1.4.0 has not shipped.

## Example

After preparing the Docker image and confirming its image ID via `docker image inspect`:

```bash
locdex benchmark run-local \
  --repo . \
  --manifest benchmarks/tasks/py-arithmetic-edge-001.yaml \
  --image sha256:REPLACE_WITH_FULL_64_HEX_IMAGE_ID \
  --model smoke \
  --model-path /absolute/path/to/model.gguf \
  --output local-trial.json
```

The example image ID is a placeholder; no working image is distributed in this stage.

The output is a **metadata-only** result with task ID, pinned commit, model and image digests, mode, status, wall time, step budget, and visible/hidden grader booleans. It contains no prompts, generated source, file paths, credentials or raw model output. Only `status: passed` and both grader outcomes passing count as success.

## Known limitations

- The runner currently supports the owned **Python pilot fixture only** and local GGUF execution. Cloud-only and hybrid benchmarking, more languages, broader isolation tests, repeat trials and model comparisons remain outstanding.
- Docker isolation depends on the daemon, host configuration, and its supported security controls. This is not a general-purpose untrusted-code execution service.
- Container image reproducibility and local model/backend performance still require hands-on qualification.
- Do not mount Docker sockets, host credentials, personal directories, telemetry secrets or hidden grader files into an agent container.
- No comparative performance claims can be drawn from a single model attempt or fixture.

For the broader protocol, see [LOCDEXBENCH_DESIGN.md](LOCDEXBENCH_DESIGN.md) and [Issue #15](https://github.com/Locdex/Locdex/issues/15).
