# Locdex v1.4.1 — patch candidate

**Status:** Source candidate undergoing CI and review. Public registry publication is separate from merging this branch.

Locdex v1.4.1 improves the interactive terminal, multi-agent orchestration checks and safe worktree integration while maintaining the v1.4 local-first coding-agent architecture.

## Changes

- **Welcome screen:** responsive terminal panel displaying Locdex version, selected model, repository, permissions, sandbox and common commands. ANSI color is enabled only on a compatible interactive terminal; narrow terminals receive a compact variant.
- **Multi-agent planning:** `locdex agents plan --config ... --parallel N` previews deterministic dependency waves and agent model assignments without loading models or writing repositories.
- **Safer downstream integration:** identical upstream edits arriving through multiple dependency branches no longer create false conflicts; divergent edits remain blocked.
- **Accurate conflict reporting:** later edits by a downstream agent to a file originally edited by its ancestor no longer appear as competing independent changes.
- **Execution visibility:** supervisor events report the starting batch and per-agent outcome. Invalid parallel worker counts or unsafe absolute/traversing write scopes are rejected.
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

## Release policy

Version `1.4.1` must be published to PyPI before publishing the npm wrapper, because `@locdex/cli@1.4.1` installs exactly `locdex==1.4.1`. A Git tag, GitHub Release and npm registry publication are not inferred from a successful source merge. Model-free orchestration validation is not a substitute for a successful full model-driven coding task on declared supported hardware.

The full comparative LocdexBench remains experimental and is not reported as a stable coding accuracy score.
