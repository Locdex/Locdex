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

- Docker Desktop (Windows) running **Linux containers**, with sufficient RAM assigned to Docker, or a Linux Docker engine. The runner is CPU-only in the first milestone.
- A checkout of `main` with the benchmark fixture commit in Git history.
- A local Python 3.10–3.12 `.venv` created from this checkout (editable installation).
- An installed model such as `qwen25-3b` or `qwen25-7b`. The discontinued development-only `smoke` model is not required.

The provided [Dockerfile](Dockerfile) builds a local image containing the current Locdex checkout, Python 3.11, Git and a CPU-only `llama-cpp-python` wheel. Initial image construction downloads dependencies; actual benchmark trials **never download models**, never invoke cloud inference, and use `--network none`.

The runner uses the built image's **immutable ID**, not a mutable image tag. The mounted GGUF file stays on the host and is read-only in the agent container.

## First benchmark on Windows (PowerShell)

After installing Docker Desktop and the selected model, use the repository's virtual environment:

```powershell
git switch main
git pull --ff-only origin main
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
locdex model install qwen25-3b
.\scripts\bench_local.ps1 -Model qwen25-3b -MemoryGb 8
```

The setup script performs five checks/actions: confirms Docker and the managed GGUF path, validates the pinned fixture, builds the CPU image, verifies llama.cpp inside a network-disabled container, and invokes `locdex benchmark run-local` with the immutable image ID.

For an already-installed Qwen2.5-Coder 7B model, increase the container cap if Docker has enough RAM:

```powershell
.\scripts\bench_local.ps1 -Model qwen25-7b -MemoryGb 12 -SkipBuild
```

The `-SkipBuild` flag reuses an existing `locdex-bench:local` image. Rebuild after changing Locdex source code to ensure the image includes the latest version. Test smaller models first if available RAM is limited. The CPU may require several minutes per attempt.

## Direct CLI invocation

The PowerShell helper is optional. Following a successful `docker build`:

```powershell
docker build --platform linux/amd64 -f benchmarks/Dockerfile -t locdex-bench:local .
$imageId = (docker image inspect --format '{{.Id}}' locdex-bench:local).Trim()
$ggufPath = (locdex model status qwen25-3b | ConvertFrom-Json).path
locdex benchmark run-local --repo . --manifest benchmarks/tasks/py-arithmetic-edge-001.yaml --image $imageId --model qwen25-3b --model-path $ggufPath --memory-gb 8 --output local-trial.json
```

The metadata-only output includes the task ID, pinned commit, model/image digests, local-only mode, status, container memory limit, elapsed time, step cap, and visible/hidden grader booleans. It contains no prompts, source code, paths or model output. Only passing independent verification qualifies as success. A single attempt is a **functional trial**, not a comparative quality score.

## Known limitations

- The runner currently supports the owned **Python pilot fixture only** and local GGUF execution. Cloud-only and hybrid benchmarking, more languages, broader isolation tests, repeat trials and model comparisons remain outstanding.
- Docker isolation depends on the daemon, host configuration, and its supported security controls. This is not a general-purpose untrusted-code execution service.
- Container image reproducibility and local model/backend performance still require hands-on qualification.
- Do not mount Docker sockets, host credentials, personal directories, telemetry secrets or hidden grader files into an agent container.
- No comparative performance claims can be drawn from a single model attempt or fixture.

For the broader protocol, see [LOCDEXBENCH_DESIGN.md](LOCDEXBENCH_DESIGN.md) and [Issue #15](https://github.com/Locdex/Locdex/issues/15).
