# Contributing to Locdex

Thanks for taking the time to test or contribute to Locdex.

Locdex is still early, so reports from real developer machines and real repositories are especially valuable. You do not need to submit code to make a useful contribution.

## Useful Contributions

We especially welcome:

- installation and setup reports;
- hardware/backend compatibility reports;
- reproducible agent failures;
- context or routing problems;
- safety and permission-boundary issues;
- model-profile experiments;
- documentation improvements;
- focused pull requests with tests.

## Reporting a Bug

When possible, include:

- operating system and version;
- Python version;
- system RAM;
- CPU;
- GPU/accelerator, if any;
- selected Locdex model;
- runtime/backend selected by Locdex;
- repository language/framework;
- the task you asked Locdex to perform;
- what you expected;
- what actually happened;
- a minimal reproduction if one is practical.

Please remove secrets, private source code, API keys, tokens, personal data, and proprietary information before posting logs or screenshots.

## Hardware Reports

Hardware reports are particularly useful right now.

Please include the output of relevant status commands where safe:

```bash
locdex runtime status
locdex model status
```

Also tell us whether:

- `locdex setup` completed successfully;
- the accelerated backend loaded;
- Locdex fell back to CPU;
- the selected model completed a smoke test;
- interactive coding tasks were usable on your machine.

## Development Setup

Clone the repository:

```bash
git clone https://github.com/Locdex/Locdex.git
cd Locdex
```

Create and activate a Python 3.10–3.12 virtual environment, then install Locdex with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

Run Ruff:

```bash
ruff check .
```

## Pull Requests

Keep pull requests focused.

A good PR should:

1. explain the problem being solved;
2. avoid unrelated refactors;
3. include or update tests when behaviour changes;
4. preserve workspace and Git safety boundaries;
5. update documentation when user-facing behaviour changes;
6. pass the existing test suite and Ruff checks.

For substantial architectural changes, opening an issue first is encouraged so the design can be discussed before a large implementation is written.

## Safety Boundaries

Changes must not silently weaken Locdex's current safety model.

In particular:

- file operations should remain constrained to the workspace unless a design change is explicitly reviewed;
- protected `.git` internals should remain inaccessible to ordinary agent file tools;
- general command execution must not become a bypass for guarded Git operations;
- staging, commit, pull, and push operations should continue to respect explicit user intent;
- telemetry must not begin collecting raw prompts or source code by default.

If your contribution intentionally changes one of these boundaries, call it out prominently in the pull request.

## Model and Runtime Changes

When proposing a new model profile or runtime backend, please include:

- upstream model/runtime source;
- license information;
- expected RAM/VRAM requirements;
- approximate download size;
- supported quantization or build;
- target operating systems/hardware;
- how you tested it;
- known limitations.

## Commit Messages

Use concise, descriptive commit messages. Examples:

```text
Fix CUDA runtime selection on older drivers
Add regression test for Git intent gating
Document Vulkan fallback setup
```

## Questions

If you are unsure whether something is a bug, hardware limitation, model limitation, or design issue, opening an issue is still useful.

The goal is to make Locdex reliable across more machines and more real-world coding workflows.
