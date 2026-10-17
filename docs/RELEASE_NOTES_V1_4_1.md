# Locdex v1.4.1 — release notes

**Status:** Source release acceptance passed on 17 October 2026; GitHub Release and registry publication pending.

Locdex v1.4.1 improves the interactive terminal, multi-agent orchestration checks and safe worktree integration while maintaining the v1.4 local-first coding-agent architecture.

## Changes

- **Welcome screen:** responsive terminal panel displaying Locdex version, selected model, repository, permissions, sandbox and common commands. ANSI color is enabled only on a compatible interactive terminal; narrow terminals receive a compact variant.
- **Multi-agent planning:** `locdex agents plan --config ... --parallel N` previews deterministic dependency waves and agent model assignments without loading models or writing repositories.
- **Safer downstream integration:** identical upstream edits arriving through multiple dependency branches no longer create false conflicts; divergent edits remain blocked.
- **Accurate conflict reporting:** later edits by a downstream agent to a file originally edited by its ancestor no longer appear as competing independent changes.
- **Execution visibility:** supervisor events report the starting batch and per-agent outcome. Invalid parallel worker counts or unsafe absolute/traversing write scopes are rejected.
- **Qwen2.5-Coder 3B small-model editing:** schema-valid, compact edit instructions encourage the local model to request a concrete edit. Until a write succeeds, the action schema permits tools or escalation but not an unsupported final answer. Existing tool permissions, sandbox restrictions, verification and rollback remain enforced.
- **Update notifications:** optional nonblocking, cached update checks show a short notice with one upgrade command appropriate to the installation channel. Updates are never installed automatically.
- **npm documentation:** the public package README contains user-facing installation instructions rather than maintainer publishing checklists.
- **Test coverage:** scheduling, conflict and warm-start adjacent tests are included in the supported Python/macOS/Linux/Windows CI matrix.

## Validation

The deterministic multi-agent tests use mock agent decisions and real temporary Git worktrees. They verify scheduling, dependency handoff, and conflict handling **without** asserting local-model coding quality. Real agent orchestration remains dependent on installed models, memory and hardware.

Example:

```powershell
locdex agents plan --config examples/agents/low-memory-smoke.yaml --parallel 2
python -m pytest tests/test_multiagent_v33.py tests/test_multiagent_patch.py
```

See [multi-agent orchestration](MULTIAGENT.md) for execution and worktree review.

### Verified local coding-agent acceptance — 17 October 2026

A live Qwen2.5-Coder 3B Instruct Q4_K_M run using Locdex's native Windows CPU runtime completed the release smoke task in **two model decisions**. In a temporary Git repository with an intentionally incorrect `is_even` function, the agent requested a `replace_in_file` edit, performed the edit under its normal permission and sandbox rules, and passed built-in compile and test verification.

The independent release probe confirmed:

| Check | Observed result |
| --- | --- |
| Agent status | `completed` |
| Agent steps | 2 |
| Independent unit tests | 4/4 passed |
| Source-file changes | `math_utils.py` only |
| Original test-file checksum | Unchanged |
| Built-in verification | Compile and tests passed; lint skipped |
| Model initialization | 206.7 seconds |
| First decision | 419.6 seconds |
| Second decision | 24.9 seconds |
| Total release probe | 840.2 seconds |

The correction changed the modulo comparison from odd-number detection to even-number detection. The result demonstrates **one verified local model-driven coding task**, not a general coding-task success rate, a benchmark leaderboard, or validated multiagent model performance. Slow CPU inference and model initialization remain important limitations on memory-constrained machines.

The reproducible probe is `scripts/release_smoke_qwen25_3b.ps1`. The source CI matrix also passed across supported Linux, Windows and macOS environments.

## Release policy

Version `1.4.1` must be published to PyPI before publishing the npm wrapper, because `@locdex/cli@1.4.1` installs exactly `locdex==1.4.1`. A Git tag, GitHub Release and npm registry publication are not inferred from a successful source merge. Model-free orchestration validation is not a substitute for a successful full model-driven coding task on declared supported hardware.

The full comparative LocdexBench remains experimental and is not reported as a stable coding accuracy score.
