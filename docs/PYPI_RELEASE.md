# Locdex v1.4 release procedure — stable in development

## Release status and package identity

| Track | Version | State |
| --- | --- | --- |
| Prior stable | `v1.3.1` | Published |
| v1.4 testing prerelease | `v1.4.0a1` / PyPI `locdex==1.4.0a1` / npm `@locdex/cli@1.4.0-alpha.1` | Published prerelease |
| v1.4 stable target | `v1.4.0` / PyPI `locdex==1.4.0` / npm `@locdex/cli@1.4.0` | **Under development; not published** |

The v1.4 prerelease and v1.4 stable target implement the **same architecture**. The alpha exists for testing, bug fixing and release qualification. This document records the prerelease procedure below; **do not repeat its alpha publication steps to create the future stable release**.

- PyPI project: `locdex`
- Canonical repository: `Locdex/Locdex`
- Trusted Publisher workflow: `.github/workflows/pypi-release.yml`

Normal unpinned installation may select the previous stable version; use an explicit version when testing the v1.4 alpha. The npm prerelease must pin the corresponding PyPI prerelease. See [v1.4 stable release gates](V1_4_STABLE_ROADMAP.md).

## v1.4.0a1 prerelease verification (historical)

From a clean checkout of the intended release commit:

```powershell
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
python -m pip install --no-deps --force-reinstall dist\locdex-1.4.0a1-py3-none-any.whl
locdex --version
```

Review source archives and the executable files included in the wheel. Review the CI matrix, platform support, changelog, and user-facing documentation before publishing. PyPI files are immutable: correcting a bad release requires a *new* version.

The `Python distribution validation and PyPI release` workflow builds the sdist and wheel in an unprivileged job. On a published GitHub Release it verifies the exact `v`-prefixed version tag before uploading build artifacts and delegates upload to a minimal Trusted Publishing job.

## Register GitHub Trusted Publishing on PyPI

The existing PyPI project is administered by an authorized maintainer at https://pypi.org/manage/projects/ . Under the project's **Publishing** settings, register this GitHub Actions Trusted Publisher:

| Field | Value |
|---|---|
| Owner | `Locdex` |
| Repository | `Locdex` |
| Workflow file | `pypi-release.yml` |
| Environment | `pypi` |

Before releasing, configure a GitHub Actions environment named `pypi` for the repository, restrict deployment to approved tags, and require maintainer review where GitHub repository settings support it. Ensure the workflow exists on the default branch `main`.

No PyPI API key needs to be stored in GitHub or in the codebase. The PyPI publishing job requests a short-lived OIDC credential from GitHub Actions.

## v1.4.0a1 prerelease publication steps (completed)

1. Confirm the package source and Python/npm versions match; build both distribution formats; pass the full CI matrix.
2. Merge the reviewed release commit, including `.github/workflows/pypi-release.yml`, into `main` without changing its intended version.
3. Add the PyPI Trusted Publisher to the **existing** `locdex` project and configure the `pypi` environment in GitHub.
4. Create and publish a GitHub Release with tag `v1.4.0a1` pointing to the reviewed release commit. The release workflow verifies the tag/version relationship and publishes with Trusted Publishing. This step is intentionally manual.
5. Verify https://pypi.org/project/locdex/1.4.0a1/ and install in a clean virtual environment:
   ```powershell
   py -3.11 -m venv .venv-release-check
   .\.venv-release-check\Scripts\python.exe -m pip install "locdex==1.4.0a1"
   .\.venv-release-check\Scripts\locdex.exe --version
   ```
6. Once PyPI succeeds, publish the matching public npm prerelease with the `next` dist-tag; verify npm installs the managed Python version.

The above v1.4.0a1 release was published and should remain historically accurate. Do not rerun a released tag to substitute new stable artifacts.

## Next: stable v1.4.0 release (not yet published)

1. Complete and document the [v1.4 stable acceptance gates](V1_4_STABLE_ROADMAP.md), using the prerelease for real-world testing.
2. On a reviewed release commit, change `pyproject.toml` to `version = "1.4.0"` and change the npm wrapper package version to `1.4.0` plus its Python pin to `locdex==1.4.0`; update tests and changelog together.
3. Verify clean installs, fresh wheel/source archives, CI, supported platforms, installation guides, and task-level agent behavior. Do not reuse the prerelease artifacts.
4. Create a **new** Git tag `v1.4.0` and a **non-prerelease** GitHub Release once stable release approval is given. GitHub's PyPI Trusted Publishing workflow must verify the tag exactly matches `pyproject.toml`.
5. Validate `pip install "locdex==1.4.0"` after PyPI publication; then publish `@locdex/cli@1.4.0` on npm as the stable `latest` channel after its independent acceptance tests. Never repoint `latest` at an alpha.
6. Announce v1.4 stable only after the actual GitHub, PyPI and npm release records exist.

The version bump to `1.4.0` is deliberately deferred; the repository's current `1.4.0a1` metadata must continue to identify the published testing build until stable release work is approved.
