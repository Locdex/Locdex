# LocdexBench: proposal and v0 implementation plan

**Status: proposed, not yet implemented, as part of v1.4 stable development.** Stable v1.3.1 is the previous release; v1.4.0a1 is a testing prerelease of the same v1.4 architecture that will underpin stable v1.4.0. Locdex `model qualify` is a tiny runtime/agent acceptance probe. It must never be renamed or advertised as a LocdexBench score. This document defines the first genuinely comparative evaluation.

## The question

Measure **what completed useful coding work**, under what resource and privacy constraints, for each of:
- **local-only**: Locdex + one local model; network disabled
- **cloud-only**: same Locdex tools/harness with one explicitly configured cloud model (external API costs recorded)
- **hybrid**: Locdex local-first plus opt-in cloud fallback (local and cloud outcomes attributed separately)

Benchmark the **agent stack** and the **underlying model** separately. Do not attribute a hybrid solve to its local model alone. A cheap model that works only with a cloud rescue is not equivalent to a local-only solve.

## Minimal suite: LocdexBench v0

Start with **5 owned/licensed fixtures** that run quickly without network access:

1. Python unit bug: arithmetic edge case (single file, regression tests)
2. Python multi-file import/API regression (requires navigation, multiple files)
3. TypeScript pure-function bug (single module, node:test or existing fixture dependency)
4. TypeScript API/type compatibility regression (multi-file edit)
5. Python + TypeScript small interface mismatch (cross-file reasoning)

All tasks start from fixed **commit SHAs**, use pinned tools/dependencies, and have *visible* tests plus *held-out* tests kept **outside** the agent's workspace. Do not ingest arbitrary third-party repositories until task licenses, dependencies, secrets and reproducibility have been audited.

A task manifest v0 (planned YAML format):

```yaml
suite: locdexbench-v0
id: py-arithmetic-edge-001
category: bugfix
language: python
license: MIT
fixture: fixtures/py-arithmetic-edge-001
base_commit: "<full SHA of fixed buggy fixture snapshot>"
task: "Fix handling of zero and negative values without changing the public API."
setup:
  command: ["python", "-m", "pip", "install", "--no-index", "-r", "requirements.txt"]
  offline: true
visible_checks:
  - ["python", "-m", "pytest", "-q", "tests/test_visible.py"]
hidden_grader: graders/py-arithmetic-edge-001
limits:
  wall_seconds: 600
  model_steps: 12
  max_output_tokens: 4096
  max_context_tokens: 8192
  network: false
```

The example is a schema sketch, **not an executable or graded task**. Before first runner implementation, freeze a machine-validatable v0 schema, allowed commands and a fixture licensing policy. Never let an agent see or edit held-out grader files.

## Runner pipeline and trust boundaries

```text
versioned task manifest + fixture checksum + model/backend manifest
                      |
                 validate input
                      |
       verify buggy baseline fails relevant tests
       verify gold patch passes tests; negative mutation fails
                      |
          disposable clean Git checkout/worktree
                      |
       isolated agent container / bounded execution
       OFFLINE unless explicit cloud-only/hybrid mode
                      |
            agent patch + tool outcomes
                      |
         immutable snapshot of final workspace
                      |
   fresh isolated verifier (visible and held-out tests)
   grader located outside agent-accessible workspace
                      |
         allowlisted metadata-only run record
                      |
       private report -> opt-in sanitized export
```

**Security:** A writable working tree and logical sandbox are **not** sufficient to execute untrusted code safely. The runner must use independent OS/container sandboxing and explicit isolation of host secrets, file mounts and network. Never run newly downloaded benchmark fixtures unconfined on a maintainer's laptop. All grading commands are fixed by fixture maintainers, not composed from model output. Ensure graders do not read the developer's home directory or Git credentials.

Task validation must fail closed when: baseline passes unexpectedly; gold fix fails; tests are missing/rewritten; task commit differs; protected files change; grader becomes visible to agent; or setup needs unapproved network access.

## Evaluation rules and metrics

Each published result includes suite version, selected task IDs/checksums, Locdex Git SHA, model ID **and exact GGUF revision/quantization**, provider/backend, hardware tier, context/output limits, tool permission mode, sandbox details, seed/sampling, wall budget, dependency lock/hash, and run failure reason.

Capture in a private local record and publicly export only approved fields:

- **Verified solve rate**: held-out grader passes and invariant/protected-file checks pass, with an unambiguous denominator
- **Pass@1**, plus repeated-attempt statistics when trials > 1; report n and confidence intervals
- **Time-to-verification**: wall seconds, cold-load and generation times where measured
- **Cost per successful task**: billable input/output tokens and provider pricing snapshot; mark unknown, do not invent
- **Efficiency**: input/output tokens, retrieval/context sizes, attempts and tool invocations (only where measured)
- **Reliability**: timeouts, invalid tool calls, failures to preserve tests, canceled/rolled-back attempts
- **Routing**: local success, cloud rescue, and routing regret vs measured paired alternatives

Report failures, exclusions and censored timeouts. Disclose whether a run is cold or warm. Never use model-produced statements like "fixed" as the primary label.

## Pairing, fairness and validity

- Start **each trial from the same bugged commit**, with workspace/repository state reset.
- Use consistent step and wall budgets, same tool policy and same task prompt; disclose any mode-specific network rule.
- For stochastic models, use **3 trials** per task/model/mode initially, and report uncertainty; do not equate `temperature=0` with guaranteed reproducibility.
- Freeze the task set before model comparisons; avoid tuning prompts to a particular model after seeing hidden test results.
- Report the difference between total hybrid cost and paid API cost, and include local time/energy separately when estimable.
- Do not train a router on data that leaks grader outcomes for its evaluation task set; hold out task families and repositories.

## Proposed implementation sequence

| Phase | Deliverable | Exit criterion |
| --- | --- | --- |
| **0. Protocol (first)** | Task schema v0; sanitizer schema; fixture licensing and safety checklist | One manifest validated; exact fields and grading policy peer-reviewed |
| **1. Runner MVP** | Disposable fixture runner, host/container boundary, baseline+gold validation, immutable output snapshot | One seeded Python defect consistently fails before fix and passes with gold patch |
| **2. Five tasks** | 2 Python, 2 TypeScript, 1 cross-language task; hidden graders | All fixtures deterministic in offline CI; cheating/test editing detected |
| **3. Trials and reporting** | 3 repeated trials per task/model/mode; JSONL runs; grouped summary | Failed and timed-out trials counted; zero sensitive source in publishable output |
| **4. Routing evidence** | Paired local/cloud/hybrid dataset; cost/quality/latency tradeoff dashboard | Router compared to actual alternatives and baseline, not just selected-route telemetry |

The **first PR after this spec** should be a *manifest parser/validator + one deliberately failing Python fixture + protected out-of-repo grader*, with tests for accepted and rejected manifests. The next PR adds the isolated runner and gold-patch validation. **Do not start with an expensive leaderboard or an AI-generated benchmark dataset**: establish reproducibility and isolation first.

## Funding and ownership

[Funding roadmap](../docs/FUNDING_AND_ROADMAP.md) associates support goals with this engineering work, but public benchmark eligibility and rankings are **independent** of sponsorship. All benchmark methodology, fixture provenance, grader version and sanitized results should be public after review; never publish private prompts, credentials or raw user repositories.
