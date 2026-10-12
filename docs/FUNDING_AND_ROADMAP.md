# Support Locdex: funding and engineering milestones

Locdex is an open-source, local-first coding-agent project. Sponsorship helps fund maintainers' engineering time, reproducible evaluations, documentation, CI, and—in later phases—representative test hardware. Funding does not buy access to private source code or influence security findings and published benchmark results.

> **Status:** Proposed sponsorship tiers and funding targets; **not** active payment tiers or guaranteed deadlines. GitHub payment tiers are created on an approved GitHub Sponsors profile, not in `.github/FUNDING.yml`. The funding configuration references the maintainer GitHub account (`bandojayy`); until that account has an approved Sponsors profile and the repository's **Sponsorships** feature is enabled, this file alone does not activate payments. Organization sponsorships could replace the maintainer link later.

## Suggested monthly tiers

| Monthly tier | Suggested GitHub Sponsors title | What support helps advance | Sponsor recognition |
| --- | --- | --- | --- |
| **$5** | Community supporter | Maintain installation guides, reproducible bug reports, first-run fixes | Optional supporter acknowledgement |
| **$15** | Developer backer | LocdexBench v0 fixture library and test-verification harness | Optional monthly progress notes |
| **$50** | Benchmark sponsor | Paired local-only/cloud-only/hybrid runs; methodology and public reporting | Optional acknowledgement on funding page |
| **$150** | Infrastructure partner | CI matrix, Windows/Linux/macOS compatibility, bounded inference reliability | Optional public supporter credit |
| **$500** | Research & engineering sponsor | Model-routing evaluations, hardware access, reproducible datasets and integrations | Optional supporter highlight, without editorial control |

These describe the *development priorities supported by the whole sponsorship pool*. They are **not feature purchases, contractual milestones, SLAs, or a guarantee that one sponsor's payment covers the stated work**. All core security, model routing, and benchmark methodology remain open and independently reviewed. Acknowledgements require sponsor opt-in.

## Transparent collective funding goals

Illustrative **sustained monthly** funding thresholds; progress is counted from actual recurring monthly commitments, never from the number of sponsors or unreceived pledges. Reassess costs and targets publicly before announcing any campaign goal.

| Sustained monthly support | Targeted milestone | Definition of done |
| --- | --- | --- |
| **$250/mo** | M0: developer experience and project health | Install smoke tests across supported Python versions; issue templates; validated guides; regression triage |
| **$750/mo** | M1: **LocdexBench v0** | Public spec and versioned fixture set; isolated task runner; clean baseline/gold validations; per-run manifest and failure reporting |
| **$2,000/mo** | M2: comparative **LocdexBench v0.1** | Repeatable paired runs, stable task selection, held-out graders, separate local/cloud/hybrid cohorts, sanitizer + uncertainty reporting |
| **$5,000/mo** | M3: hardware and routing evaluation | Multiple hardware tiers, verified performance/cost budgets, router-regret analysis, reproducible CI evaluation and documented limitations |

Funding may require sustained support over multiple months; these thresholds are planning targets, not linear cost estimates. If funding stays below target, the team can still work on milestones as time permits. Public status updates should report *work completed, blockers, expenses by category, and next acceptance criteria*, not fabricated performance gains.

## Immediate roadmap (unfunded work can still proceed)

**M0 — release reliability and local-model onboarding**
- Keep PyPI/npm versions in sync and maintain alpha release validation.
- One reliable quickstart for CPU, constrained-memory systems, and standard developer machines.
- Runtime failures should have actionable diagnostics and test coverage.

**M1 — LocdexBench v0 (next)**
- Version and validate a manifest for 5–10 small, owned/licensed Python and TypeScript bug-fix tasks.
- Snapshot clean fixture repositories at a known commit; verify that the supplied bug fails and a gold fix passes.
- Build a disposable, offline-first runner; keep held-out verification outside the agent workspace.
- Run the same tasks with fixed budgets and report successes **and** failures.

**M2 — meaningful comparisons**
- Expand to at least 20 validated tasks spanning bug fixes, multi-file changes and tests.
- Repeat stochastic trials; report pass@1, cost/solved, time/solved, tool errors, timeout rate and confidence ranges.
- Compare local-only, cloud-only and hybrid separately. Do not credit cloud completions to local models.

**M3 — improve routing based on evidence**
- Evaluate model-selection policies on paired tasks, not just observational production telemetry.
- Measure quality/latency/cost trade-offs and router regret; publish model/backend/hardware context.
- Add regression gates for privacy, protected tests, rollback and safe cancellation.

The benchmark design is in [`benchmarks/LOCDEXBENCH_DESIGN.md`](../benchmarks/LOCDEXBENCH_DESIGN.md). This file states *planned* work; it does not claim LocdexBench or any score has shipped.

## Configure GitHub Sponsors

1. Apply to **GitHub Sponsors** for the account that will receive payouts (maintainer `bandojayy`, or an eligible project organization). Complete payout, tax, and 2FA requirements and wait for approval.
2. Set up and **publish** the payment tiers from the table above in the Sponsors dashboard; edit the proposed amounts and rewards to fit actual capacity.
3. In repository Settings → General → Features, enable **Sponsorships**. Ensure `.github/FUNDING.yml` on `main` points to the **active approved** account.
4. Link the Sponsors profile to this roadmap. Add a public quarterly milestone update and transparent status labels to the roadmap/issues.
5. If there is no active approved Sponsors profile, do not tell users the payment button works. Change the funding account only once a verified recipient is ready.

Project-related support must not be characterized as a charitable donation or used to promise special benchmark placement.
