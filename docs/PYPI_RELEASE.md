# PyPI release procedure

## Distribution identity

- PyPI project: `locdex`
- Existing public stable version: `1.3.1` (published before the current architecture work)
- Next architecture preview: `1.4.0a1`
- npm companion release: `@locdex/cli@1.4.0-alpha.1` (installs exactly `locdex==1.4.0a1`)
- Canonical repository: `Locdex/Locdex`
- Trusted Publisher workflow: `.github/workflows/pypi-release.yml`

The preview is a prerelease: `pip install locdex` normally selects a stable version, whereas `pip install locdex==1.4.0a1` installs this preview. The npm wrapper pins the exact preview.

## Verification

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

## Release sequence

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

Do not trigger the release event until the Trusted Publisher and environment are configured, the artifact validation workflow is green, and the maintainer has reviewed the release.
