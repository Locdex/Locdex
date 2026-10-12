# Sponsorship and Development Roadmap

Locdex is an open-source, local-first coding agent focused on repository intelligence, efficient model execution, controlled tool use, and verifiable software changes. Community support contributes to engineering, testing, documentation, and the infrastructure needed to maintain the project.

## Project status

**Locdex v1.4 stable is under development.** Version **v1.3.1** remains the previous stable release, while **v1.4.0a1** is the published testing prerelease of the same v1.4 architecture.

The current priorities are local-model compatibility, agent reliability, predictable cloud escalation, and a reproducible evaluation framework through LocdexBench. Progress is tracked through the [v1.4 roadmap](V1_4_STABLE_ROADMAP.md) and the repository's [issues](https://github.com/Locdex/Locdex/issues).

## What sponsorship supports

| Area | Scope | Expected project outcome |
| --- | --- | --- |
| Installation and developer experience | Runtime compatibility, model setup, clear diagnostics, release automation | More reliable onboarding across supported systems |
| Agent reliability and security | Permissions, workspace isolation, verification, cancellation, rollback | Safer and more predictable code modifications |
| LocdexBench | Licensed task fixtures, isolated execution, held-out graders, published methodology | Reproducible evidence of task-level coding performance |
| Model routing and efficiency | Local/cloud comparisons, bounded context, latency and cost analysis | Better-informed model selection without mandatory cloud dependence |
| Continuous maintenance | Regression testing, issue triage, compatibility updates and documentation | Sustainable open-source development |

Sponsorship supports shared project priorities, not exclusive functionality or favorable treatment in benchmarks.

## Sponsorship levels

The following are **proposed monthly contribution levels**. Available tiers and benefits are determined by the published [GitHub Sponsors profile](https://github.com/sponsors/bandojayy), where eligible. Contributions are voluntary and do not constitute service agreements or guaranteed delivery dates.

| Monthly support | Level | Area supported |
| --- | --- | --- |
| **$5** | Community Supporter | Documentation, issue triage and accessibility of local-model setup |
| **$15** | Developer Backer | Maintenance, test fixtures and contributor workflows |
| **$50** | Benchmark Supporter | LocdexBench methodology, reproducible trials and reporting |
| **$150** | Infrastructure Partner | CI, cross-platform qualification and runtime reliability |
| **$500** | Research Supporter | Broader evaluations, hardware access and routing research |

Public acknowledgements may be offered with sponsor consent. Financial support does **not** provide control over security disclosures, benchmark selection, results, product architecture, or editorial decisions.

## Development milestones

These milestones represent planned engineering outcomes. Funding levels below are **illustrative targets for sustained aggregate monthly support**, not confirmed revenue or automatic completion triggers.

| Funding target | Milestone | Acceptance criteria |
| --- | --- | --- |
| **$250/month** | **M0 — Release quality** | Documented installation checks, reproducible regressions and improved onboarding |
| **$750/month** | **M1 — LocdexBench v0** | Validated task manifests, licensed fixtures, isolated evaluation and baseline/gold verification |
| **$2,000/month** | **M2 — Comparative evaluation** | Repeated local-only, cloud-only and hybrid trials with independent grading and sanitized results |
| **$5,000/month** | **M3 — Hardware and routing evaluation** | Multiple hardware tiers, documented cost/latency metrics and comparative routing analysis |

Milestone sequencing depends on engineering capacity, technical results, and available resources. Development may proceed independently of reaching a funding target. None of these targets is presented as achieved.

## Roadmap for v1.4

**Release quality:** Validate Python and npm installation paths, model setup, timeout handling and supported operating-system configurations.

**Agent reliability:** Strengthen guarded file operations, task continuation, session handling, permissions, test preservation, verification and rollback.

**LocdexBench:** Establish a trustworthy benchmark protocol before reporting comparative scores. The [LocdexBench design](../benchmarks/LOCDEXBENCH_DESIGN.md) defines fixture provenance, independent grading, isolation, attribution and reporting requirements.

**Routing and efficiency:** Use controlled evaluation results to assess model-selection quality, cloud fallback behavior and context economics. Production telemetry alone is not a valid comparative benchmark.

**Stable release:** Publish v1.4.0 following the [stable-release criteria](V1_4_STABLE_ROADMAP.md). The v1.4.0a1 prerelease and the stable target share one architectural direction.

## Accountability and transparency

Project progress is documented through version-controlled specifications, GitHub issues, pull requests, CI runs, and release notes. Benchmark results will be reported only when reproducible and independently verifiable. Published results must distinguish local-only successes from cloud-assisted outcomes and disclose material limitations.

Funding may support maintainers' time, computing resources, testing infrastructure and distribution costs. Proposed goals are planning estimates rather than audited budgets, delivery commitments or charitable donation representations.

## Support the project

- [View the source code and open issues](https://github.com/Locdex/Locdex)
- [Review the v1.4 release roadmap](V1_4_STABLE_ROADMAP.md)
- [Explore LocdexBench](../benchmarks/LOCDEXBENCH_DESIGN.md)
- [GitHub Sponsors](https://github.com/sponsors/bandojayy)

Sponsorship availability depends on the payment options enabled on GitHub Sponsors.
