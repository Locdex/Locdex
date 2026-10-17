# Multi-agent orchestration

Locdex executes independently configured coding agents in separate Git worktrees. Dependencies determine the execution order; independent agents can run concurrently when sufficient compute and memory are available. Changes are not automatically committed or merged.

## Inspect an execution plan without model inference

A deterministic planner validates agent definitions and produces the same dependency-aware scheduling waves without downloading/loading GGUF files, changing the repository, or creating worktrees.

```powershell
locdex agents validate --config examples/agents/low-memory-smoke.yaml
locdex agents plan --config examples/agents/low-memory-smoke.yaml --parallel 2
locdex agents plan --config examples/agents/low-memory-smoke.yaml --parallel 2 --json
```

The bundled [low-memory smoke specification](../examples/agents/low-memory-smoke.yaml) contains two independent read-only analysts and a downstream verifier. The planner schedules `inspect` and `tests` together, then `report` after both finish. The planner does not demonstrate coding performance; it verifies the orchestration graph and constraints.

## Execute the agents

Execution requires a clean Git working tree, installed model profiles, and a compatible inference backend:

```powershell
locdex model install smoke
locdex runtime install --backend auto
locdex agents run --config examples/agents/low-memory-smoke.yaml --parallel 1
```

The low-memory smoke profile is for functionality checks, not a coding-quality claim. A memory-constrained CPU may require considerable time to load even a small model. Each agent currently loads its own model process; `--parallel 1` is the safest initial choice on 8 GB-class systems. The interactive CLI's warm model worker does not currently apply to independent multi-agent worktrees.

For workloads that require edits, each agent may specify `permission_mode`, `sandbox_mode`, a relative `write_scope`, `max_steps` and dependencies. Any agent with interactive `ask` permissions requires serial execution and a live approval callback. Noninteractive/JSON runs cannot approve interactive prompts.

## Execution and integration semantics

- Worktrees are created from the current Git commit in Locdex's managed cache. The base repository remains unchanged.
- The scheduler chooses runnable agents by descending priority and configuration order, with no more than eight concurrent workers.
- Changes from successful upstream dependencies are inherited into downstream worktrees. Identical transitive changes may be inherited through multiple parents; divergent edits to the same path block downstream integration.
- Failures prevent dependent agents from starting. Independent branches may still complete.
- Intentional follow-up edits along the same dependency chain are not flagged as competing parallel changes in the final integration report.
- The command outputs worktree paths and branches for review. No final agent branch is auto-committed or auto-merged.

## Reproducible tests

The deterministic orchestration regressions are independent of model inference:

```powershell
python -m pytest tests/test_multiagent_v33.py tests/test_multiagent_patch.py
```

End-to-end model runs must be evaluated separately on declared hardware, reporting actual results and failures. Model loading, plan success and passing mocked orchestration tests are not equivalent to verified coding-task completion.
