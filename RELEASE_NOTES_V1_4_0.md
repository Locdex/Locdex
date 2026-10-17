# Locdex v1.4.0

Locdex v1.4 introduces the next stable architecture for the open-source, local-first coding agent. The Agent and Model Runtime are separate layers: the agent manages repository context, tools, permissions and verification, while the runtime manages local GGUF inference and optional configured cloud providers.

## Highlights

- **Interactive warm model worker.** The terminal starts the selected local model in a separate process while remaining responsive. Once initialized, that worker is reused across sequential tasks in the same interactive session, and is unloaded on model change or exit. The `/status` command reports worker state.
- **Repository-aware coding.** Targeted source retrieval, bounded multi-step tool decisions, code-change verification, checkpoints and guarded rollback are available in the agent runtime.
- **Permission and sandbox controls.** Tool authorization, protected-file checks, capability reporting and explicit cloud opt-in remain separate from model decisions.
- **Local and hybrid execution.** Managed GGUF profiles use llama.cpp; authorized external providers can be configured separately. Local-only execution remains available without an API key.
- **Experimental LocdexBench v0 tooling.** An audited Python fixture, baseline/reference/negative controls, offline Docker execution and checksum-verified Docker-native GGUF caching support subsequent evaluation work. [Preliminary infrastructure measurements](benchmarks/RESULTS_V0_PRELIMINARY.md) are published as diagnostics, not coding accuracy scores.
- **Python and npm.** Matching `locdex==1.4.0` and `@locdex/cli@1.4.0` packages use the same Python-based agent implementation; npm provides the launcher/bootstrap.

## Compatibility

- Python 3.10–3.12.
- Windows, macOS and Linux; actual sandbox protection varies by host capabilities.
- npm launcher: Node.js 18+ with a supported Python installation.
- Local models require separately installed llama.cpp runtime and GGUF weights.

## Known limitations

- Model startup speed and token generation depend on available system RAM, CPU/GPU, disk throughput and context configuration. CPU-only inference on older hardware can be slow.
- Asynchronous warm loading is **process-local** to the interactive CLI; independent `locdex task` processes still perform their own model initialization.
- The warm worker cannot generate tokens before model initialization completes. A model-load deadline is enforced when inference is requested; interactive idle-time eviction and a cross-terminal model daemon are not part of this version.
- On a constrained Windows/Docker configuration, local Qwen2.5-Coder 3B benchmarking did not complete a verified task within the trial budget. The project does **not** claim a LocdexBench task-success score or public leaderboard for this release.
- Windows and macOS native sandbox capability reporting does not imply complete network/filesystem isolation against untrusted code.

## Resources

- [Local model installation and runtime guidance](docs/QUICKSTART_LOCAL_MODELS.md)
- [v1.4 architecture and release scope](docs/V1_4_STABLE_ROADMAP.md)
- [LocdexBench v0 development protocol](benchmarks/README.md)
- [Runtime lifecycle development](https://github.com/Locdex/Locdex/issues/33)
