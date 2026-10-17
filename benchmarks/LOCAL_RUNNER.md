# LocdexBench v0 — Isolated Local Trial Runner

**Status:** Experimental local-only runner. It is a development tool, **not** a public leaderboard, and no model scores have been released. The live Docker/GGUF path still requires validation on representative hardware before stable v1.4.

## Isolation model

A benchmark attempt uses three separate processes:

1. A **disposable Git workspace** containing only an audited and commit-pinned fixture, never the grader or reference patches.
2. A **locked-down Docker agent container** with the workspace as its sole writable bind mount and the GGUF on a Docker-native volume mounted read-only (after checksum verification). Networking is disabled, Linux capabilities dropped, root filesystem read-only, process/memory/CPU limits applied, and cloud inference plus telemetry uploads disabled.
3. A **separate grading container** with the candidate workspace mounted read-only. The held-out grader is mounted only into the grading container; it is never accessible to the agent.

The runner checks changed files against the explicit per-task allowlist before grading. A timed-out or failed attempt does not receive a pass. No local subprocess fallback is available if Docker or the pinned image is missing.

A task's fixed baseline and gold/negative controls are validated separately by `python scripts/validate_benchmark_fixtures.py`. That command only executes reviewed repository-owned tests, not arbitrary model output.

## Prerequisites

- Docker Desktop (Windows) running **Linux containers**, with sufficient RAM assigned to Docker, or a Linux Docker engine. The runner is CPU-only in the first milestone.
- A checkout of `main` with the benchmark fixture commit in Git history.
- A local Python 3.10–3.12 `.venv` created from this checkout (editable installation).
- An installed model such as `qwen25-3b` or `qwen25-7b`. The discontinued development-only `smoke` model is not required.

The provided [Dockerfile](Dockerfile) builds a local image containing the current Locdex checkout, Python 3.11, Git and a CPU-only `llama-cpp-python` wheel. Initial image construction downloads dependencies. The builder uses `docker buildx build --load` to copy the finished image from BuildKit into the local Docker image store, including when Docker Desktop uses the `docker-container` driver. Without `--load`, `docker image inspect` may fail even after a successful build. Actual benchmark trials **never download models**, never invoke cloud inference, and use `--network none`.

The runner uses the built image's **immutable ID**, not a mutable image tag. The host GGUF stays unchanged. The runner stages a checksum-keyed copy into a persistent Docker-native volume, validates its SHA-256 before each trial, and mounts that volume read-only into the agent container. The grader never receives the model volume. The first transfer from Windows storage can be slow, but subsequent trials reuse the verified copy.

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

The helper confirms Docker and the managed GGUF path, validates the pinned fixture, builds the CPU image, verifies llama.cpp inside a network-disabled container, and invokes `locdex benchmark run-local` with the immutable image ID. Before running the agent, the runner stages or reuses the model in Docker-native storage and verifies its SHA-256.

For an already-installed Qwen2.5-Coder 7B model, increase the container cap if Docker has enough RAM:

```powershell
.\scripts\bench_local.ps1 -Model qwen25-7b -MemoryGb 12 -SkipBuild
```

The `-SkipBuild` flag reuses an existing `locdex-bench:local` image. Rebuild after changing Locdex source code to ensure the image includes the latest version. Test smaller models first if available RAM is limited. The CPU may require several minutes per attempt.

## Reuse an already staged Docker GGUF volume

If you've already copied the exact Qwen GGUF into a Docker volume under the filename `model.gguf`, you can reuse that volume without another Windows-to-Docker transfer. For example:

```powershell
$env:LOCDEX_BENCH_CONTEXT_TOKENS = "4096"  # non-standard low-memory diagnostic
.\scripts\bench_local.ps1 -Model qwen25-3b -MemoryGb 6 -ModelVolume locdex-qwen25-3b-native -SkipBuild
```

The runner compares SHA-256 of the volume's `/models/model.gguf` against the selected local model **before executing the agent**. An absent, corrupt, or mismatching user-supplied volume fails closed; it is never overwritten or deleted. When `-ModelVolume` is omitted, LocdexBench uses a persistent checksum-keyed cache, stages automatically on a cache miss and verifies the cached GGUF before every run. Staging and integrity verification are infrastructure operations excluded from the timed agent trial; cold and warm setup costs should be reported separately when relevant.

The volume contains an **additional full copy of the GGUF**. Remove unused cache volumes deliberately using `docker volume rm <name>` only after confirming they are no longer needed. The model cache remains local, the agent is offline, and graders cannot access it. Reduced-context experiments change benchmark conditions and should not be reported as standard-model scores.

## Direct CLI invocation

The PowerShell helper is optional. Following a successful `docker buildx build --load`:

```powershell
docker buildx build --load --platform linux/amd64 -f benchmarks/Dockerfile -t locdex-bench:local .
$imageId = (docker image inspect --format '{{.Id}}' locdex-bench:local).Trim()
$ggufPath = (locdex model status qwen25-3b | ConvertFrom-Json).path
locdex benchmark run-local --repo . --manifest benchmarks/tasks/py-arithmetic-edge-001.yaml --image $imageId --model qwen25-3b --model-path $ggufPath --memory-gb 8 --output local-trial.json
```

The metadata-only output includes the task ID, pinned commit, model/image digests, local-only mode, status, container memory limit, elapsed time, step cap, and visible/hidden grader booleans. It contains no prompts, source code, paths or model output. Only passing independent verification qualifies as success. A single attempt is a **functional trial**, not a comparative quality score.

## Progress and timeout diagnostics

The agent phase prints elapsed-time heartbeats approximately every 15 seconds. These are process-liveness messages, **not** proof that the model has generated tokens or finished agent steps. Raw model and tool output is deliberately withheld from terminal progress and benchmark records.

When an output path is supplied, the runner writes an additional local-only `<trial>.diagnostics.json` file containing the current execution stage, timeout flag, elapsed agent time and exit code when known. The public `locdexbench-local-v0` result schema remains unchanged. Neither file includes the model's private responses.

During a diagnostic trial, the runner relays bounded `[Agent]` and `[Inference]` phase events from the container, without printing raw model responses or file content. Phase events now distinguish CLI startup, hardened-agent workspace preparation, deterministic retrieval planning, direct GGUF model initialization, base-agent context preparation, decision generation and tool actions. The hardened agent loads its model **before** it enters the base agent; a prolonged `model_loading` phase can therefore precede any numbered step. The inference-timeout environment variable does not enforce a deadline in this direct-session path. The local-only diagnostic sidecar records the last reported event, inferred last observable phase, event count and stderr byte count (no raw stderr). These phase events identify loading, generation, step selection, and tool invocation when those events are emitted, but do not measure per-token throughput.

To use an explicit inference phase deadline, set `$env:LOCDEX_INFERENCE_TIMEOUT_SECONDS = "300"` in PowerShell before invoking `bench_local.ps1`. This override is forwarded **only to the agent container**, not the grader. IMPORTANT: the benchmark's current coding agent uses the direct synchronous `LlamaCppSession`, **not** the qualification runner's `IsolatedLlamaCppSession`. Thus the variable reaches the container but does **not currently enforce** a per-inference hard timeout for this coding-agent route. The outer benchmark wall-time remains the only hard cutoff here. Treat the variable as diagnostic configuration, not an effective timeout extension, until the agent runtime is migrated to enforceable per-phase deadlines.

A timeout during the agent stage is recorded as `agent_execution`. Grading stages are identified separately. The standard 600-second task budget remains unchanged.

### Low-memory CPU diagnostic (non-standard)

On memory-constrained Docker Desktop machines, opt in to a reduced model context for an **experimental diagnostic only**:

```powershell
$env:LOCDEX_BENCH_CONTEXT_TOKENS = "4096"
.\scripts\bench_local.ps1 -Model qwen25-3b -MemoryGb 6
```

The override affects only the agent container and does not change Qwen's default 6,144-token context profile, the task's overall wall-time limit, or hidden grading isolation. It changes model conditions, so report it separately from standard results; a smaller context might truncate useful prompt history or fail a task requiring more context. The reduced window is **not a proven fix for slow model loading**. To disable it after diagnosis, use `Remove-Item Env:LOCDEX_BENCH_CONTEXT_TOKENS -ErrorAction SilentlyContinue`.

## Known limitations

- The runner currently supports the owned **Python pilot fixture only** and local GGUF execution. Cloud-only and hybrid benchmarking, more languages, broader isolation tests, repeat trials and model comparisons remain outstanding.
- Docker isolation depends on the daemon, host configuration, and its supported security controls. This is not a general-purpose untrusted-code execution service.
- Container image reproducibility and local model/backend performance still require hands-on qualification.
- Do not mount Docker sockets, host credentials, personal directories, telemetry secrets or hidden grader files into an agent container.
- No comparative performance claims can be drawn from a single model attempt or fixture.

For the broader protocol, see [LOCDEXBENCH_DESIGN.md](LOCDEXBENCH_DESIGN.md) and [Issue #15](https://github.com/Locdex/Locdex/issues/15).
